import os
import sys
import platform
import re
import random
import socket
import smtplib
import threading
import time
import html
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from typing import List, Tuple, Dict, Set, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from email.utils import parseaddr
import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed

class EmailVerifier:
    """
    Advanced Email Verification with SMTP checking and quality scoring
    Based on the original emailverifier.py with all features intact
    """
    
    def __init__(self, enable_smtp: bool = True, max_workers: int = 16, quick_mode: bool = True):
        self.enable_smtp = enable_smtp
        self.max_workers = max_workers
        self.quick_mode = quick_mode
        
        # Configuration
        self.smtp_timeout =15
        self.smtp_helo_domain = self._get_smart_helo_domain()
        self.smtp_mail_from = f"probe@{self.smtp_helo_domain}"
        
        # Caches with thread locks
        self._mx_cache: Dict[str, Tuple[List[str], str]] = {}
        self._mx_lock = threading.Lock()
        self._smtp_cache: Dict[str, Tuple[int, str, str]] = {}
        self._smtp_lock = threading.Lock()
        
        # Patterns and constants
        self.email_regex = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,24}$", re.I)
        
        # High-reputation consumer inbox domains
        self.high_rep_domains: Set[str] = {
            "gmail.com", "googlemail.com",
            "outlook.com", "hotmail.com", "live.com", "msn.com",
            "yahoo.com", "ymail.com", "rocketmail.com",
            "icloud.com", "me.com", "mac.com",
            "proton.me", "protonmail.com", "aol.com", "zoho.com"
        }
        
        # Guarded/hosted providers
        self.guarded_hints = (
            "aspmx", ".l.google.com", "googlemail.com",
            ".protection.outlook.com", "yahoodns.net",
            "mimecast.com", "stackmail.com", "ionos.co.uk", "gandi.net"
        )
        
        # Asset and suspicious patterns
        self.asset_tlds = {
            "png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "js", "css", "map", "json",
            "woff", "woff2", "ttf", "eot", "otf", "pdf"
        }
        self.suspicious_local_pat = re.compile(r"^[a-f0-9]{24,}$", re.I)
        
        # SMTP soft temporary failure codes and patterns
        self.soft_temp_codes = {421, 450, 451, 452}
        self.soft_temp_text = ("temporarily deferred", "try again later", "greylist", "rate limit", "temporarily unavailable")
    
    def _get_smart_helo_domain(self) -> str:
        """Get the best HELO domain - try to detect actual ISP domain"""
        
        # Method 1: Try to get actual FQDN first
        try:
            fqdn = socket.getfqdn()
            if ('.' in fqdn and 
                not any(x in fqdn.lower() for x in ['local', 'desktop-', 'laptop-', 'pc-', 'workgroup'])):
                return fqdn
        except Exception:
            pass
        
        # Method 2: Try to get ISP domain from public IP reverse DNS
        try:
            import urllib.request
            # Get public IP
            with urllib.request.urlopen('http://ipinfo.io/ip', timeout=5) as response:
                public_ip = response.read().decode().strip()
            
            # Try reverse DNS lookup on public IP
            hostname = socket.gethostbyaddr(public_ip)[0]
            if ('.' in hostname and 
                not any(x in hostname.lower() for x in ['local', 'internal', 'private'])):
                # Extract domain from hostname
                parts = hostname.split('.')
                if len(parts) >= 2:
                    isp_domain = '.'.join(parts[-2:])  # Get last two parts (domain.tld)
                    return isp_domain
        except Exception:
            pass
        
        # Method 3: Fallback to rotating legitimate domains
        safe_domains = ['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com']
        return random.choice(safe_domains)
    
    def normalize_email(self, raw: str) -> str:
        """Normalize email: remove mailto:, query/fragment/pipe, spaces/quotes, common obfuscations."""
        if raw is None or (isinstance(raw, float) and str(raw) == 'nan'):
            return ""
        e = str(raw).strip()
        e = re.sub(r"^mailto:", "", e, flags=re.I)
        # Cut off everything after ?, #, | or whitespace
        e = re.split(r"[?#|\s]", e, maxsplit=1)[0]
        # Undo common obfuscations
        e = (e.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
               .replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", "."))
        # Remove stray spaces and quotes
        e = e.replace(" ", "").strip(").,;:>]}\"'")
        return e.lower()
    
    def is_valid_email_format(self, email: str) -> bool:
        return bool(self.email_regex.match(email))
    
    def email_host(self, email: str) -> str:
        try:
            return email.split("@", 1)[1].lower()
        except Exception:
            return ""
    
    def email_local(self, email: str) -> str:
        try:
            return email.split("@", 1)[0].lower()
        except Exception:
            return ""
    
    def looks_like_asset_or_id(self, email: str) -> bool:
        """Filter junk like globe@2x.webp or long tracking ids."""
        if not email or "@" not in email:
            return True
        host = self.email_host(email)
        if not host or "." not in host:
            return True
        tld = host.rsplit(".", 1)[-1].lower()
        if tld in self.asset_tlds:
            return True
        if re.search(r"@\d+x\.(?:png|jpe?g|webp|gif|svg|ico)$", email, re.I):
            return True
        local = self.email_local(email)
        if self.suspicious_local_pat.match(local):
            return True
        return False
    
    def provider_is_guarded(self, mx_joined: str) -> bool:
        s = (mx_joined or "").lower()
        return any(k in s for k in self.guarded_hints)
    
    def resolve_mx(self, domain: str) -> Tuple[List[str], str]:
        """Resolve MX with cache, sorted by preference; fallback to A record if no MX."""
        domain = (domain or "").lower().strip()
        with self._mx_lock:
            if domain in self._mx_cache:
                return self._mx_cache[domain]
        
        try:
            answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
            # sort by preference (lowest first), strip trailing dots
            hosts = [str(r.exchange).rstrip('.') for r in sorted(answers, key=lambda r: r.preference)]
            res = (hosts, "mx_ok")
        except dns.resolver.NoAnswer:
            # some domains accept mail on A record
            try:
                dns.resolver.resolve(domain, 'A', lifetime=self.smtp_timeout)
                res = ([domain], "mx_fallback_a")
            except Exception:
                res = ([], "no_mx")
        except Exception:
            res = ([], "no_mx")
        
        with self._mx_lock:
            self._mx_cache[domain] = res
        return res
    
    def smtp_check_address(self, mx_host: str, rcpt: str) -> Tuple[bool, str, bool]:
        """
        returns (accepted, note, tempfail)
          - accepted: True if RCPT responded 250/251
          - note:     'rcpt_250', 'timeout', 'mailfrom_451', ...
          - tempfail: True if 4xx/timeout/soft text → retry advisable
        """
        try:
            server = smtplib.SMTP(mx_host, 25, timeout=self.smtp_timeout)
            server.set_debuglevel(0)
            # EHLO first; fall back to HELO
            code, _ = server.ehlo(self.smtp_helo_domain)
            if not (200 <= code < 300):
                code, _ = server.helo(self.smtp_helo_domain)
            
            # Opportunistic STARTTLS
            try:
                if server.has_extn("starttls"):
                    server.starttls()
                    server.ehlo(self.smtp_helo_domain)
            except Exception:
                pass
            
            # MAIL FROM
            code, _ = server.mail(self.smtp_mail_from)
            if code >= 400:
                try: 
                    server.quit()
                except Exception: 
                    pass
                return False, f"mailfrom_{code}", (code in self.soft_temp_codes)
            
            # RCPT TO
            code, msg = server.rcpt(rcpt)
            accepted = code in (250, 251)
            note = f"rcpt_{code}"
            msg_l = (msg or b"").decode(errors="ignore").lower() if isinstance(msg, (bytes, bytearray)) else str(msg).lower()
            is_temp = (code in self.soft_temp_codes) or any(h in msg_l for h in self.soft_temp_text)
            
            try: 
                server.quit()
            except Exception: 
                pass
            
            return accepted, note, is_temp

        except (socket.timeout, smtplib.SMTPServerDisconnected):
            return False, "timeout", True
        except smtplib.SMTPConnectError:
            return False, "connect_fail", True
        except smtplib.SMTPHeloError:
            return False, "helo_error", False
        except smtplib.SMTPRecipientsRefused:
            return False, "rcpt_refused", False
        except Exception:
            return False, "smtp_error", True
    
    def verify_email_smtp(self, email: str) -> Tuple[int, str, str]:
        """Verify email using SMTP with caching, quick mode by default."""
        with self._smtp_lock:
            if email in self._smtp_cache:
                return self._smtp_cache[email]

        # Early junk/format guard
        if not self.is_valid_email_format(email) or self.looks_like_asset_or_id(email):
            res = (0, "invalid", "format_or_asset")
            with self._smtp_lock:
                self._smtp_cache[email] = res
            return res

        domain = self.email_host(email)
        if not domain:
            res = (0, "invalid", "no_domain")
            with self._smtp_lock:
                self._smtp_cache[email] = res
            return res

        mx_hosts, mx_note = self.resolve_mx(domain)
        if not mx_hosts:
            res = (30, "no_mx", mx_note)
            with self._smtp_lock:
                self._smtp_cache[email] = res
            return res

        accepted_any = False
        temp_seen = False
        notes = [mx_note]

        attempts = 1 if self.quick_mode else 3
        for mx in mx_hosts[:3]:
            for attempt in range(attempts):
                ok, note, is_temp = self.smtp_check_address(mx, email)
                notes.append(f"{mx}:{note}")
                temp_seen |= is_temp
                if ok:
                    accepted_any = True
                    break
                if not self.quick_mode and is_temp and attempt + 1 < attempts:
                    # tiny backoff
                    time_sleep = 0.4 * (attempt + 1) + random.random() * 0.2
                    time.sleep(time_sleep)
                    continue
                break
            if accepted_any:
                break

        catchall = False
        # Skip catch-all probe in quick mode (huge speedup)
        if accepted_any and not self.quick_mode:
            probe_local = "catchall_probe_%d" % (random.randint(100000, 999999))
            probe_addr = "%s@%s" % (probe_local, domain)
            for mx in mx_hosts[:2]:
                ok2, note2, temp2 = self.smtp_check_address(mx, probe_addr)
                notes.append(f"probe:{note2}")
                if ok2 and not temp2:
                    catchall = True
                    break

        joined = "; ".join(notes[:8])

        if accepted_any and not catchall:
            res = (85 if self.quick_mode else 90, "deliverable", joined)
        elif accepted_any and catchall:
            res = (75, "catchall_suspected", joined)
        else:
            hard_reject = any(("rcpt_550" in n) or ("rcpt_551" in n) for n in notes)
            if hard_reject:
                res = (40, "rejected", joined)
            else:
                if temp_seen or self.provider_is_guarded(joined):
                    res = (70, "temporary_fail_retry", joined)
                elif "no_mx" in joined:
                    res = (30, "no_mx", joined)
                else:
                    res = (55, "unverifiable_provider_neutral", joined)

        with self._smtp_lock:
            self._smtp_cache[email] = res
        return res
    
    def verify_email_simple(self, email: str) -> Tuple[int, str, str]:
        """
        Simple, fast checks without SMTP:
          - Format
          - MX presence  
          - Light reputation bump for well-known inbox providers
        """
        email = email.strip()
        if not self.is_valid_email_format(email) or self.looks_like_asset_or_id(email):
            return (0, "invalid", "format_or_asset")

        domain = self.email_host(email)
        if not domain:
            return (0, "invalid", "no_domain")

        mx_hosts, mx_note = self.resolve_mx(domain)
        if not mx_hosts:
            return (30, "no_mx", "no_mx_records")

        base_score = 70
        status = "domain_ok"
        if domain in self.high_rep_domains:
            base_score = 80
            status = "domain_ok_highrep"

        return (base_score, status, "mx=%s" % ",".join(mx_hosts[:3]))
    
    def verify_email(self, email: str) -> Tuple[bool, str]:
        """
        Main verification method that returns simple boolean result
        Compatible with the FastAPI interface
        """
        email = self.normalize_email(email)
        if not email:
            return False, "Empty email"
        
        if self.enable_smtp:
            quality, status, notes = self.verify_email_smtp(email)
        else:
            quality, status, notes = self.verify_email_simple(email)

        # Convert quality score to boolean
        is_valid = quality >= 85  # Stricter threshold for considering email deliverable
        return is_valid, f"{status} (quality: {quality})"

    def verify_email_advanced(self, email: str) -> Dict[str, Any]:
        """Return structured verification details for pipeline workflows."""
        normalized = self.normalize_email(email)
        if not normalized:
            return {
                'email': email,
                'valid': False,
                'quality': 0,
                'status': 'invalid',
                'notes': 'empty_email'
            }

        if self.enable_smtp:
            quality, status, notes = self.verify_email_smtp(normalized)
        else:
            quality, status, notes = self.verify_email_simple(normalized)

        return {
            'email': normalized,
            'valid': quality >= 85,
            'quality': quality,
            'status': status,
            'notes': notes
        }
    
    def verify_bulk(self, emails: List[str]) -> List[Dict[str, Any]]:
        """Verify multiple emails using thread pool and return structured results."""
        results: List[Dict[str, Any]] = []

        def verify_single(email: str) -> Dict[str, Any]:
            normalized = self.normalize_email(email)
            if not normalized:
                return {
                    'email': email,
                    'valid': False,
                    'quality': 0,
                    'status': 'invalid',
                    'notes': 'empty_email'
                }

            return self.verify_email_advanced(normalized)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_email = {executor.submit(verify_single, email): email for email in emails}
            for future in as_completed(future_to_email):
                email = future_to_email[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    results.append({
                        'email': email,
                        'valid': False,
                        'quality': 0,
                        'status': 'error',
                        'notes': str(exc)
                    })

        return results

class BlogChecker:
    """
    Advanced Blog Detection and Recent Content Analysis
    Based on the original checkforblogpage.py with comprehensive detection algorithms
    """
    
    def __init__(self, max_workers: int = 30, timeout: int = 15):
        self.max_workers = max_workers
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Date extraction patterns
        self.date_patterns = [
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}",
            r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}",
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",
            r"\b20\d{2}\b"
        ]
    
    def extract_dates(self, text: str) -> List[datetime]:
        """Enhanced date extraction with better accuracy and filtering"""
        dates = []
        current_year = datetime.now().year
        
        # Enhanced date patterns with better specificity
        enhanced_patterns = [
            # Full month name patterns
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
            
            # Abbreviated month patterns
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4}\b",
            r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{4}\b",
            
            # ISO date format
            r"\b\d{4}-\d{2}-\d{2}\b",
            
            # Slash formats (with year validation)
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",
            r"\b\d{4}/\d{1,2}/\d{1,2}\b",
        ]
        
        for pattern in enhanced_patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            for date_str in matches:
                parsed_date = None
                
                # Try multiple format patterns
                format_patterns = [
                    "%B %d, %Y", "%B %d %Y", "%d %B %Y",
                    "%b %d, %Y", "%b %d %Y", "%d %b %Y", 
                    "%b. %d, %Y", "%b. %d %Y", "%d %b. %Y",
                    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"
                ]
                
                for fmt in format_patterns:
                    try:
                        parsed_date = datetime.strptime(date_str.strip('.,'), fmt)
                        
                        # Filter out unrealistic dates
                        if (parsed_date.year >= 2000 and 
                            parsed_date.year <= current_year + 1 and
                            1 <= parsed_date.month <= 12 and
                            1 <= parsed_date.day <= 31):
                            dates.append(parsed_date)
                        break
                    except ValueError:
                        continue
        
        # Remove duplicates and sort by date
        unique_dates = list(set(dates))
        unique_dates.sort(reverse=True)  # Most recent first
        
        return unique_dates[:10]  # Limit to 10 most recent dates
    
    def is_blog_page(self, soup, url: str) -> Tuple[bool, int, List[str]]:
        """
        Improved blog detection with reduced false positives
        Returns (is_blog, score, indicators)
        """
        score = 0
        indicators = []
        
        # First, check for obvious non-blog patterns (exclusion rules)
        if self._is_non_blog_page(soup, url):
            return False, -10, ["non_blog_detected"]
        
        # 1. Strong URL-based indicators (more specific patterns)
        url_lower = url.lower()
        
        # High-confidence URL patterns
        strong_url_patterns = ['/blog/', '/blogs/', '/articles/', '/posts/', '/news/', '/journal/']
        if any(pattern in url_lower for pattern in strong_url_patterns):
            score += 8
            indicators.append("strong_url_pattern")
        
        # Medium-confidence URL patterns
        medium_url_patterns = ['blog.', 'news.', 'articles.']
        if any(url_lower.startswith(pattern) for pattern in medium_url_patterns):
            score += 5
            indicators.append("medium_url_pattern")
        
        # Weak URL patterns (reduced weight)
        weak_url_patterns = ['blog', 'article', 'post', 'journal', 'magazine']
        if any(pattern in url_lower for pattern in weak_url_patterns):
            score += 2
            indicators.append("weak_url_pattern")
        
        # 2. Enhanced HTML structure indicators
        # Look for semantic article tags
        article_tags = soup.find_all('article')
        if article_tags:
            # Check if articles have blog-like structure
            blog_article_count = 0
            for article in article_tags:
                if self._is_blog_like_article(article):
                    blog_article_count += 1
            
            if blog_article_count > 0:
                score += min(blog_article_count * 3, 8)  # Cap at 8 points
                indicators.append("semantic_articles")
        
        # More specific blog class patterns
        specific_blog_classes = [
            'post-content', 'blog-post', 'entry-content', 'article-content',
            'post-body', 'blog-entry', 'single-post', 'blog-article'
        ]
        
        blog_class_found = False
        for class_pattern in specific_blog_classes:
            if soup.find(class_=re.compile(class_pattern, re.I)):
                score += 4
                indicators.append("specific_blog_classes")
                blog_class_found = True
                break
        
        # Fallback to generic classes (lower weight)
        if not blog_class_found:
            generic_classes = ['post', 'entry', 'article']
            for element in soup.find_all(['div', 'section'], class_=re.compile('|'.join(generic_classes), re.I)):
                # Additional validation for generic classes
                if self._validate_blog_element(element):
                    score += 2
                    indicators.append("validated_generic_classes")
                    break
        
        # 3. Enhanced content indicators
        text = soup.get_text().lower()
        
        # Strong blog-specific phrases
        strong_blog_keywords = [
            'posted by', 'written by', 'published by', 'author:', 'by author',
            'read more', 'continue reading', 'full article', 'view comments',
            'leave a comment', 'post comment', 'share this post'
        ]
        strong_keyword_count = sum(1 for keyword in strong_blog_keywords if keyword in text)
        if strong_keyword_count > 0:
            score += min(strong_keyword_count * 2, 6)  # Cap at 6 points
            indicators.append("strong_blog_keywords")
        
        # 4. Publication date indicators (more specific)
        publication_date_score = self._detect_publication_dates(soup, text)
        if publication_date_score > 0:
            score += publication_date_score
            indicators.append("publication_dates")
        
        # 5. Blog listing indicators (multiple posts)
        blog_listing_score = self._detect_blog_listing(soup)
        if blog_listing_score > 0:
            score += blog_listing_score
            indicators.append("blog_listing")
        
        # 6. Enhanced navigation indicators
        nav_score = self._analyze_blog_navigation(soup)
        if nav_score > 0:
            score += nav_score
            indicators.append("blog_navigation")
        
        # 7. Meta and structured data indicators
        meta_score = self._analyze_blog_metadata(soup)
        if meta_score > 0:
            score += meta_score
            indicators.append("blog_metadata")
        
        # 8. Comment system detection
        comment_score = self._detect_comment_system(soup, text)
        if comment_score > 0:
            score += comment_score
            indicators.append("comment_system")
        
        # 9. RSS/Feed indicators
        feed_score = self._detect_feeds(soup)
        if feed_score > 0:
            score += feed_score
            indicators.append("rss_feeds")
        
        # Enhanced threshold - require higher confidence
        is_blog = score >= 8  # Increased from 4 to 8
        return is_blog, score, indicators

    def _is_non_blog_page(self, soup, url: str) -> bool:
        """Detect obvious non-blog pages to reduce false positives"""
        url_lower = url.lower()
        text = soup.get_text().lower()
        
        # E-commerce indicators
        ecommerce_indicators = [
            'add to cart', 'buy now', 'shopping cart', 'checkout', 'product price',
            'add to basket', 'purchase', 'order now', 'price:', '$', '€', '£'
        ]
        ecommerce_count = sum(1 for indicator in ecommerce_indicators if indicator in text)
        if ecommerce_count >= 3:
            return True
        
        # Landing page indicators
        landing_indicators = [
            'sign up now', 'get started', 'free trial', 'download now',
            'contact us', 'request demo', 'learn more'
        ]
        if any(indicator in text for indicator in landing_indicators) and len(text.split()) < 500:
            return True
        
        # Documentation/API pages
        doc_indicators = ['api documentation', 'getting started', 'installation', 'configuration']
        if any(indicator in text for indicator in doc_indicators):
            return True
        
        # Homepage/About pages (short content)
        if any(path in url_lower for path in ['/about', '/home', '/contact', '/services']):
            if len(text.split()) < 300:  # Short pages are likely not blogs
                return True
        
        return False

    def _is_blog_like_article(self, article_element) -> bool:
        """Check if an article element has blog-like characteristics"""
        article_text = article_element.get_text()
        
        # Check for typical blog post length (at least 100 words)
        if len(article_text.split()) < 100:
            return False
        
        # Look for blog post indicators within the article
        blog_indicators = [
            'posted', 'published', 'written by', 'author', 'read more',
            'continue reading', 'comments', 'share'
        ]
        
        article_lower = article_text.lower()
        indicator_count = sum(1 for indicator in blog_indicators if indicator in article_lower)
        
        return indicator_count >= 1

    def _validate_blog_element(self, element) -> bool:
        """Validate that a generic element is actually blog-related"""
        element_text = element.get_text()
        
        # Must have substantial content
        if len(element_text.split()) < 50:
            return False
        
        # Look for blog-specific patterns
        validation_patterns = [
            r'\b(?:posted|published|written)\s+(?:on|by)',
            r'\b(?:read more|continue reading|full post)\b',
            r'\b(?:comments?|reply|share)\b'
        ]
        
        for pattern in validation_patterns:
            if re.search(pattern, element_text, re.I):
                return True
        
        return False

    def _detect_publication_dates(self, soup, text: str) -> int:
        """Detect publication dates with higher confidence"""
        score = 0
        
        # Look for semantic date elements
        date_elements = soup.find_all(['time', 'span', 'div'], class_=re.compile(r'date|time|published', re.I))
        if date_elements:
            score += 3
        
        # Look for structured publication dates
        structured_patterns = [
            r'\bpublished\s+(?:on\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}',
            r'\bposted\s+(?:on\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}',
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\s*[-–—]\s*by\b'
        ]
        
        for pattern in structured_patterns:
            if re.search(pattern, text, re.I):
                score += 2
                break
        
        return min(score, 4)  # Cap at 4 points

    def _detect_blog_listing(self, soup) -> int:
        """Detect blog listing pages with multiple posts"""
        score = 0
        
        # Look for multiple article-like elements
        potential_posts = soup.find_all(['article', 'div'], class_=re.compile(r'post|entry|blog', re.I))
        
        valid_posts = 0
        for post in potential_posts[:10]:  # Check max 10 elements
            post_text = post.get_text()
            # Must have title-like structure and some content
            if len(post_text.split()) >= 20:
                # Look for title indicators
                if post.find(['h1', 'h2', 'h3', 'h4']) or post.find(class_=re.compile(r'title|heading', re.I)):
                    valid_posts += 1
        
        if valid_posts >= 3:
            score += 5
        elif valid_posts >= 2:
            score += 3
        
        return score

    def _analyze_blog_navigation(self, soup) -> int:
        """Analyze navigation for blog-specific elements"""
        score = 0
        
        # Look for blog-specific navigation links
        nav_elements = soup.find_all(['nav', 'ul', 'div'], class_=re.compile(r'nav|menu', re.I))
        
        blog_nav_terms = ['blog', 'articles', 'posts']
        
        for nav in nav_elements:
            nav_text = nav.get_text().lower()
            matches = sum(1 for term in blog_nav_terms if term in nav_text)
            if matches >= 2:
                score += 3
                break
            elif matches == 1:
                score += 1
        
        # Look for pagination
        pagination_indicators = ['previous', 'next', 'page', 'older posts', 'newer posts']
        page_text = soup.get_text().lower()
        if any(indicator in page_text for indicator in pagination_indicators):
            score += 2
        
        return min(score, 4)

    def _analyze_blog_metadata(self, soup) -> int:
        """Analyze meta tags and structured data for blog indicators"""
        score = 0
        
        # OpenGraph article type
        og_type = soup.find('meta', property='og:type')
        if og_type and og_type.get('content', '').lower() == 'article':
            score += 4
        
        # Article schema.org markup
        if soup.find(attrs={'itemtype': re.compile(r'schema\.org/Article', re.I)}):
            score += 3
        
        # Blog-specific meta keywords
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords:
            keywords = meta_keywords.get('content', '').lower()
            if any(term in keywords for term in ['blog', 'article', 'post']):
                score += 2
        
        return score

    def _detect_comment_system(self, soup, text: str) -> int:
        """Detect comment systems (blogs typically have comments)"""
        score = 0
        
        # Popular comment systems
        comment_systems = [
            'disqus', 'facebook-comments', 'wordpress-comments',
            'livefyre', 'intensedebate', 'commentluv'
        ]
        
        page_html = str(soup).lower()
        if any(system in page_html for system in comment_systems):
            score += 3
        
        # Generic comment indicators
        comment_patterns = [
            r'\bcomment\s*(?:form|section|area)\b',
            r'\bleave\s+a?\s*comment\b',
            r'\bpost\s+comment\b',
            r'\b\d+\s+comments?\b'
        ]
        
        for pattern in comment_patterns:
            if re.search(pattern, text, re.I):
                score += 2
                break
        
        return min(score, 4)

    def _detect_feeds(self, soup) -> int:
        """Detect RSS/Atom feeds (blogs typically have feeds)"""
        score = 0
        
        # RSS/Atom feed links
        feed_links = soup.find_all('link', {'type': re.compile(r'application/(?:rss|atom)\+xml', re.I)})
        if feed_links:
            score += 2
        
        # Feed navigation links
        feed_nav_patterns = ['rss', 'atom', 'feed', 'subscribe']
        nav_links = soup.find_all('a', href=True)
        
        for link in nav_links:
            link_text = link.get_text().lower()
            link_href = link.get('href', '').lower()
            if any(pattern in link_text or pattern in link_href for pattern in feed_nav_patterns):
                score += 1
                break
        
        return min(score, 2)

    def has_recent_content(self, soup, url: str) -> Tuple[bool, str]:
        """
        Enhanced recent content detection with reduced false positives
        Returns (has_recent, reason)
        """
        # Method 1: Enhanced date extraction with context
        text = soup.get_text(" ", strip=True)
        dates = self.extract_dates(text)
        now = datetime.now()
        
        # Look for dates in publication context (not just any date)
        publication_context_patterns = [
            r'(?:published|posted|written|created|updated)\s+(?:on\s+)?([^.]+?\d{4})',
            r'([^.]+?\d{4})\s*[-–—]\s*(?:by|author)',
            r'(?:date|time):\s*([^.]+?\d{4})'
        ]
        
        for pattern in publication_context_patterns:
            matches = re.findall(pattern, text, re.I)
            for match in matches:
                context_dates = self.extract_dates(match)
                for d in context_dates:
                    if d >= now - timedelta(days=90):  # Extended to 90 days for more coverage
                        return True, "contextual_date_found"
        
        # Fallback to any recent date
        for d in dates:
            if d >= now - timedelta(days=60):
                return True, "date_found"
        
        # Method 2: Enhanced recent indicators (more specific)
        recent_indicators = [
            r'\b(?:published|posted|updated)\s+(?:today|yesterday|this week|last week)\b',
            r'\b(?:new|latest|recent)\s+(?:post|article|blog|entry)\b',
            r'\b(?:2025|2024)\b'  # Current/recent year indicators
        ]
        
        for pattern in recent_indicators:
            if re.search(pattern, text, re.I):
                return True, "recent_indicators"
        
        # Method 3: Check for multiple recent articles with validation
        article_elements = soup.find_all(['article', 'div'], class_=re.compile(r'post|entry|blog', re.I))
        valid_articles = 0
        
        for article in article_elements[:10]:  # Check max 10 articles
            article_text = article.get_text()
            # Must have substantial content to be considered a real article
            if len(article_text.split()) >= 50:
                # Look for article indicators
                if (article.find(['h1', 'h2', 'h3']) and 
                    any(indicator in article_text.lower() for indicator in ['read more', 'continue', 'posted', 'published'])):
                    valid_articles += 1
        
        if valid_articles >= 3:
            return True, "multiple_valid_articles"
        
        # Method 4: Enhanced feed detection
        feed_links = soup.find_all('link', {'type': re.compile(r'application/(?:rss|atom)\+xml', re.I)})
        if feed_links:
            # Additional validation - check if feed link has recent indicator
            for feed in feed_links:
                feed_title = feed.get('title', '').lower()
                if any(term in feed_title for term in ['latest', 'recent', 'new']):
                    return True, "recent_feed_present"
            return True, "rss_feed_present"
        
        # Method 5: Check for "last updated" or similar indicators
        last_updated_patterns = [
            r'last\s+updated?\s*:?\s*([^.]+?\d{4})',
            r'modified\s*:?\s*([^.]+?\d{4})',
            r'updated?\s+on\s*:?\s*([^.]+?\d{4})'
        ]
        
        for pattern in last_updated_patterns:
            matches = re.findall(pattern, text, re.I)
            for match in matches:
                update_dates = self.extract_dates(match)
                for d in update_dates:
                    if d >= now - timedelta(days=180):  # More lenient for update dates
                        return True, "recent_update_date"
        
        return False, "no_recent_content"
    
    def check_single_url(self, url: str) -> Dict[str, any]:
        """
        Check a single URL for blog presence and recent content
        Returns comprehensive analysis
        """
        result = {
            'url': url,
            'is_blog': False,
            'has_recent_content': False,
            'blog_score': 0,
            'blog_indicators': [],
            'recent_reason': '',
            'error': None,
            'status_code': None
        }
        
        try:
            # Ensure URL has protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Make request
            response = requests.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
            result['status_code'] = response.status_code
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Check if it's a blog
                is_blog, blog_score, indicators = self.is_blog_page(soup, url)
                result['is_blog'] = is_blog
                result['blog_score'] = blog_score
                result['blog_indicators'] = indicators
                
                # Check for recent content
                has_recent, reason = self.has_recent_content(soup, url)
                result['has_recent_content'] = has_recent
                result['recent_reason'] = reason
            else:
                result['error'] = f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            result['error'] = "Timeout"
        except requests.exceptions.ConnectionError:
            result['error'] = "Connection failed"
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def check_multiple_urls(self, urls: List[str]) -> List[Dict[str, any]]:
        """Check multiple URLs using thread pool"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {executor.submit(self.check_single_url, url): url for url in urls}
            for future in as_completed(future_to_url):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    url = future_to_url[future]
                    results.append({
                        'url': url,
                        'is_blog': False,
                        'has_recent_content': False,
                        'blog_score': 0,
                        'blog_indicators': [],
                        'recent_reason': '',
                        'error': f"Processing error: {str(e)}",
                        'status_code': None
                    })
        
        return results


class EmailScraper:
    """Advanced email scraper with integrated verification - matches original emailscraper.py"""
    
    def __init__(self):
        self.session = self._make_session()
        self.mx_cache = {}
        self.smtp_cache = {}
        self.domain_cache = {}
        
        # Constants from original - INCREASED for better performance
        self.MAX_WORKERS = 16
        self.HTTP_TIMEOUT = 15
        self.SMTP_TIMEOUT = 15
        self.SMTP_HELO_DOMAIN = self._get_smart_helo_domain()
        self.SMTP_MAIL_FROM = f"probe@{self.SMTP_HELO_DOMAIN}"
        
        # Email patterns and hints from original
        self.EMAIL_REGEX = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,24}\b", re.I)
        self.DISPOSABLE_HINTS = {
            "gmail.com","yahoo.com","outlook.com","hotmail.com","aol.com","icloud.com",
            "proton.me","protonmail.com","live.com","msn.com","yandex.com"
        }
        self.EDITORIAL_PREFIXES = [
            "submissions@","submission@","submit@","contributors@","contributor@","contribute@",
            "editor@","editors@","editorial@","letters@","opinion@","opeds@","opiniondesk@",
            "pitch@","pitches@","tips@","newsroom@","press@","media@","pr@","communications@",
            "guest@","guestpost@","guest-post@","write@","writers@","writing@","content@","blog@"
        ]
        self.GUEST_PHRASES = [
            "write for us","guest post","guest posting","guest blogger","submit article",
            "submission guidelines","editorial guidelines","become a contributor","contribute",
            "pitch us","send us your story","guest blogging guidelines","submit your writing"
        ]
        
    def _get_smart_helo_domain(self):
        """Get smart HELO domain - simplified version"""
        try:
            fqdn = socket.getfqdn()
            if '.' in fqdn and not any(x in fqdn.lower() for x in ['local', 'desktop-', 'laptop-']):
                return fqdn
        except:
            pass
        
        # Fallback to safe domains
        safe_domains = ['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com']
        return random.choice(safe_domains)
        
    def _make_session(self):
        session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504])
        # Increased pool size for better parallel performance
        session.mount("http://", HTTPAdapter(max_retries=retries, pool_connections=128, pool_maxsize=128))
        session.mount("https://", HTTPAdapter(max_retries=retries, pool_connections=128, pool_maxsize=128))
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
            "Cache-Control": "no-cache",
        })
        return session
    
    def scrape_emails(self, urls: List[str], verify_emails: bool = True, max_emails_per_site: int = 3) -> Dict[str, Any]:
        """
        Scrape emails from URLs with integrated verification (matches original functionality)
        Max 3 emails per site by default - crawls multiple pages to find more emails
        """
        results = {
            'scraped_emails': [],
            'verified_emails': [],
            'failed_urls': [],
            'metadata': {}
        }

        # Process each URL (simplified version of original parallel processing)
        for url in urls:
            try:
                # Normalize URL
                url = self._normalize_url(url)

                # Get base URL for crawling additional pages
                base_url = self._site_root(url)
                base_url_full = f"https://{base_url}" if not url.startswith(('http://', 'https://')) else url.split('/', 3)[:3]
                if isinstance(base_url_full, list):
                    base_url_full = '/'.join(base_url_full)

                # Pages to check for more emails and social links
                # OPTIMIZED: Reduced from 7 to 3 most important pages for speed
                pages_to_check = [
                    url,  # Homepage
                    f"{base_url_full}/contact",
                    f"{base_url_full}/about",
                ]

                all_emails = set()
                all_phone_numbers = set()
                all_social_links = {}
                context_score = 0
                combined_notes = []

                # Scrape all pages with early exit when max emails found
                for page_url in pages_to_check:
                    try:
                        emails_data = self._scrape_single_url_advanced(page_url)

                        if emails_data['emails']:
                            all_emails.update(emails_data['emails'])

                            # Early exit if we have enough emails
                            if len(all_emails) >= max_emails_per_site:
                                # Still get social links and phone numbers but don't scrape more pages
                                for key, value in emails_data['social_links'].items():
                                    if value and not all_social_links.get(key):
                                        all_social_links[key] = value
                                
                                # Add phone numbers from current page
                                if emails_data.get('phone_numbers'):
                                    all_phone_numbers.update(emails_data['phone_numbers'])
                                break

                        # Merge social links (keep first non-None value found)
                        for key, value in emails_data['social_links'].items():
                            if value and not all_social_links.get(key):
                                all_social_links[key] = value

                        # Collect phone numbers from all pages
                        if emails_data.get('phone_numbers'):
                            all_phone_numbers.update(emails_data['phone_numbers'])

                        context_score = max(context_score, emails_data['context_score'])
                        if emails_data['notes']:
                            combined_notes.append(emails_data['notes'])
                    except:
                        # Skip failed pages silently
                        continue

                if all_emails:
                    # Rank emails for guest posting (from original)
                    ranked_emails = self._rank_emails_for_guestposting(
                        list(all_emails),
                        self._site_root(url),
                        context_score
                    )

                    # Limit to max_emails_per_site (default 3)
                    ranked_emails = ranked_emails[:max_emails_per_site]

                    results['scraped_emails'].extend([e[0] for e in ranked_emails])

                    if verify_emails:
                        # Verify emails using integrated SMTP verification
                        verified_batch = []
                        for email, score, role in ranked_emails:
                            verification = self._verify_email_smtp_integrated(email)
                            verified_batch.append({
                                'email': email,
                                'url': url,
                                'role': role,
                                'rank_score': score,
                                'verification': verification,
                                'notes': '; '.join(combined_notes) if combined_notes else 'crawled_multiple_pages',
                                'social_links': all_social_links,
                                'phone_numbers': list(all_phone_numbers)
                            })
                        results['verified_emails'].extend(verified_batch)
                    else:
                        for email, score, role in ranked_emails:
                            results['verified_emails'].append({
                                'email': email,
                                'url': url,
                                'role': role,
                                'rank_score': score,
                                'verification': {'quality': 70, 'status': 'not_verified', 'notes': 'verification_disabled'},
                                'notes': '; '.join(combined_notes) if combined_notes else 'crawled_multiple_pages',
                                'social_links': all_social_links,
                                'phone_numbers': list(all_phone_numbers)
                            })
                else:
                    # NEW: persist social/contact links and phone numbers even when no emails were found
                    results['verified_emails'].append({
                        'email': '',  # leave email empty as requested
                        'url': url,
                        'role': None,
                        'rank_score': 0,
                        'verification': {'quality': 0, 'status': 'no_email_found'},
                        'notes': '; '.join(combined_notes) if combined_notes else 'no_emails_found',
                        'social_links': all_social_links,
                        'phone_numbers': list(all_phone_numbers)
                    })

            except Exception as e:
                results['failed_urls'].append({'url': url, 'error': str(e)})

        # Remove duplicate emails while preserving best verification
        seen_emails = {}
        for item in results['verified_emails']:
            email = item['email']
            if email not in seen_emails or item['verification']['quality'] > seen_emails[email]['verification']['quality']:
                seen_emails[email] = item

        results['verified_emails'] = list(seen_emails.values())
        results['scraped_emails'] = list(seen_emails.keys())

        return results
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL (from original)"""
        url = (url or "").strip()
        if not url:
            return url
        if not re.match(r"^https?://", url, re.I):
            return "https://" + url
        return url
    
    def _site_root(self, url: str) -> str:
        """Extract site root (from original)"""
        if not url:
            return ""
        netloc = urlparse(url if "://" in url else "http://" + url).netloc.lower()
        return netloc.lstrip("www.")
    
    def _scrape_single_url_advanced(self, url: str) -> Dict[str, Any]:
        """Advanced URL scraping with context scoring (from original)"""
        emails = set()
        context_score = 0
        notes = ""
        phone_numbers = set()
        social_links = {
            'linkedin': None,
            'instagram': None,
            'facebook': None,
            'contact_form': None
        }

        try:
            # Fetch HTML
            response = self.session.get(url, timeout=self.HTTP_TIMEOUT, allow_redirects=True)
            if response.status_code >= 400 and url.startswith("https://"):
                # Try HTTP if HTTPS fails
                url_http = "http://" + url[len("https://"):]
                response = self.session.get(url_http, timeout=self.HTTP_TIMEOUT, allow_redirects=True)
                url = url_http

            html_text = response.text

            # Parse with BeautifulSoup (simplified - no lxml dependency)
            soup = BeautifulSoup(html_text, 'html.parser')

            # Extract from mailto links
            for link in soup.select("a[href^='mailto:']"):
                emails.add(self._normalize_email(link.get("href", "")))

            # Extract from tel: links
            for tel_link in soup.select("a[href^='tel:']"):
                tel_href = tel_link.get("href", "")
                if tel_href.startswith("tel:"):
                    raw_phone = tel_href[4:]  # Remove "tel:" prefix
                    cleaned_phone = self._normalize_phone_number(raw_phone)
                    if cleaned_phone and self._is_valid_phone_number(cleaned_phone):
                        phone_numbers.add(cleaned_phone)

            # Extract from footer
            for footer in soup.select("footer"):
                footer_text = footer.get_text(" ", strip=True)
                emails |= self._extract_emails_from_text(footer_text)
                phone_numbers |= self._extract_phone_numbers(footer_text)

            # Extract from body text
            body_text = soup.get_text(" ", strip=True)
            emails |= self._extract_emails_from_text(body_text)
            context_score = self._guest_phrase_score(body_text)

            # Extract phone numbers from body text
            phone_numbers |= self._extract_phone_numbers(body_text)

            # Extract from specific contact-related sections
            for contact_section in soup.select("section, div, aside"):
                section_class = ' '.join(contact_section.get('class', [])).lower()
                section_id = contact_section.get('id', '').lower()
                
                # Check if this section is likely to contain contact info
                if any(keyword in section_class + ' ' + section_id for keyword in 
                       ['contact', 'footer', 'info', 'address', 'phone', 'tel']):
                    section_text = contact_section.get_text(" ", strip=True)
                    phone_numbers |= self._extract_phone_numbers(section_text)

            # Extract social media links
            social_links = self._extract_social_links(soup, url)

            notes = "bs4_parse"

            # Filter out asset-like emails
            emails = {e for e in emails if not self._looks_like_asset_or_id(e)}

        except Exception as e:
            notes = f"scrape_error: {str(e)}"

        return {
            'emails': list(emails),
            'phone_numbers': list(phone_numbers),
            'context_score': context_score,
            'notes': notes,
            'social_links': social_links
        }

    def _extract_social_links(self, soup, base_url: str) -> Dict[str, Optional[str]]:
        """Extract social media and contact form links"""
        social_links = {
            'linkedin': None,
            'instagram': None,
            'facebook': None,
            'contact_form': None
        }

        # Find all links
        all_links = soup.find_all('a', href=True)

        for link in all_links:
            href = link.get('href', '').lower()

            # LinkedIn
            if 'linkedin.com' in href and not social_links['linkedin']:
                social_links['linkedin'] = href if href.startswith('http') else urljoin(base_url, href)

            # Instagram
            if 'instagram.com' in href and not social_links['instagram']:
                social_links['instagram'] = href if href.startswith('http') else urljoin(base_url, href)

            # Facebook
            if 'facebook.com' in href and not social_links['facebook']:
                social_links['facebook'] = href if href.startswith('http') else urljoin(base_url, href)

            # Contact form - look for common patterns
            if any(pattern in href for pattern in ['contact', 'get-in-touch', 'reach-us', 'connect']):
                if not social_links['contact_form']:
                    full_url = href if href.startswith('http') else urljoin(base_url, href)
                    # Avoid external links for contact forms
                    if urlparse(full_url).netloc == urlparse(base_url).netloc or urlparse(full_url).netloc == '':
                        social_links['contact_form'] = full_url

        return social_links

    def _extract_phone_numbers(self, text: str) -> Set[str]:
        """Extract phone numbers from text using comprehensive patterns"""
        if not text:
            return set()
        
        phone_numbers = set()
        
        # Common phone number patterns
        phone_patterns = [
            # US formats: (123) 456-7890, 123-456-7890, 123.456.7890, 123 456 7890
            r'\b(?:\+?1[-.\s]?)?\(?([2-9][0-8]\d)\)?[-.\s]?([2-9]\d{2})[-.\s]?(\d{4})\b',
            
            # International formats: +1 123 456 7890, +44 20 1234 5678
            r'\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
            
            # Generic patterns with common separators
            r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b',  # 123-456-7890, 123.456.7890, 123 456 7890
            r'\(\d{3}\)[-.\s]?\d{3}[-.\s]?\d{4}',  # (123) 456-7890, (123)456-7890
            
            # Toll-free numbers: 800-123-4567, 1-800-123-4567
            r'\b1?[-.\s]?[8][0][0][-.\s]\d{3}[-.\s]\d{4}\b',
            
            # Extensions: 123-456-7890 ext 123, 123-456-7890 x123
            r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\s*(?:ext?\.?\s*\d+|x\s*\d+)?\b',
        ]
        
        # Extract phone numbers using patterns
        for pattern in phone_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    # For grouped patterns, reconstruct the phone number
                    if len(match) == 3:  # (area_code, exchange, number)
                        phone = f"({match[0]}) {match[1]}-{match[2]}"
                    else:
                        phone = ''.join(match)
                else:
                    phone = match
                
                # Clean and normalize the phone number
                cleaned_phone = self._normalize_phone_number(phone)
                if cleaned_phone and self._is_valid_phone_number(cleaned_phone):
                    phone_numbers.add(cleaned_phone)
        
        # Look for phone numbers with context (more reliable)
        context_patterns = [
            r'(?:phone|tel|telephone|call|mobile|cell):\s*([+\d\s\-\.\(\)x]+)',
            r'(?:phone|tel|telephone|call|mobile|cell)\s*[:\-]?\s*([+\d\s\-\.\(\)x]+)',
            r'(?:p|t):\s*([+\d\s\-\.\(\)x]{10,})',  # "P:" or "T:" followed by digits
            r'contact.*?([+\d\s\-\.\(\)]{10,})',  # "contact" followed by phone-like string
        ]
        
        for pattern in context_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                cleaned_phone = self._normalize_phone_number(match)
                if cleaned_phone and self._is_valid_phone_number(cleaned_phone):
                    phone_numbers.add(cleaned_phone)
        
        return phone_numbers

    def _normalize_phone_number(self, phone: str) -> str:
        """Normalize phone number format"""
        if not phone:
            return ""
        
        # Remove common non-digit characters but keep + for international
        phone = re.sub(r'[^\d+x]', '', phone.lower())
        
        # Remove extensions (x followed by digits)
        phone = re.sub(r'x\d+$', '', phone)
        
        # Handle different formats
        if phone.startswith('+1') and len(phone) == 12:  # +1 followed by 10 digits
            return phone
        elif phone.startswith('1') and len(phone) == 11:  # 1 followed by 10 digits (US)
            return '+' + phone
        elif len(phone) == 10:  # Just 10 digits (US without country code)
            return '+1' + phone
        elif phone.startswith('+') and len(phone) >= 10:  # International with +
            return phone
        
        return phone

    def _is_valid_phone_number(self, phone: str) -> bool:
        """Validate if the extracted string is a valid phone number"""
        if not phone:
            return False
        
        # Remove + and count digits
        digits_only = re.sub(r'[^\d]', '', phone)
        
        # Must have at least 10 digits (US local) and at most 15 (international standard)
        if len(digits_only) < 10 or len(digits_only) > 15:
            return False
        
        # Avoid obviously invalid patterns
        # - All same digit (1111111111)
        # - Sequential numbers (1234567890)
        if len(set(digits_only)) <= 2:  # Too few unique digits
            return False
        
        # Check for common invalid patterns
        invalid_patterns = [
            '1111111111', '2222222222', '3333333333', '4444444444', '5555555555',
            '6666666666', '7777777777', '8888888888', '9999999999', '0000000000',
            '1234567890', '0987654321', '1122334455'
        ]
        
        if digits_only in invalid_patterns:
            return False
        
        return True
    
    def _extract_emails_from_text(self, text: str) -> Set[str]:
        """Extract emails from text (from original)"""
        if not text:
            return set()
        
        # Decode HTML entities and normalize
        text = html.unescape(text)
        text = text.replace("[AT]", "@").replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
        text = text.replace("[DOT]", ".").replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
        
        # Find emails with regex
        emails = set(self.EMAIL_REGEX.findall(text))
        return {self._normalize_email(e) for e in emails}
    
    def _normalize_email(self, raw: str) -> str:
        """Normalize email (from original)"""
        e = html.unescape(raw or "").strip()
        e = re.sub(r"^mailto:", "", e, flags=re.I)
        e = re.split(r"[?#|\s]", e, maxsplit=1)[0]
        e = re.sub(r"\s*(?:\[at\]|\(at\)|\sat\s)\s*", "@", e, re.I)
        e = re.sub(r"\s*(?:\[dot\]|\(dot\)|\sdot\s)\s*", ".", e, re.I)
        e = re.sub(r"\s+", "", e)
        e = e.strip(").,;:>]}\"'")
        return e.lower()
    
    def _looks_like_asset_or_id(self, email: str) -> bool:
        """Check if email looks like asset or ID (from original)"""
        host = email.split("@", 1)[-1] if "@" in email else ""
        if not host or "." not in host:
            return False
        
        tld = host.rsplit(".", 1)[-1].lower()
        asset_tlds = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "js", "css", "pdf"}
        
        if tld in asset_tlds:
            return True
            
        # Check for @2x style sprites
        if re.search(r"@\d+x\.(?:png|jpe?g|webp|gif|svg|ico)$", email, re.I):
            return True
            
        # Check for suspicious long hex-like IDs
        local = email.split("@", 1)[0]
        if re.match(r"^\w{24,}$", local):
            return True
            
        return False
    
    def _guest_phrase_score(self, text: str) -> int:
        """Score text for guest posting relevance (from original)"""
        text_lower = (text or "").lower()
        return sum(2 for phrase in self.GUEST_PHRASES if phrase in text_lower)
    
    def _rank_emails_for_guestposting(self, emails: List[str], site_host: str, context_score: int) -> List[Tuple[str, int, str]]:
        """Rank emails for guest posting potential (from original)"""
        ranked = []
        
        for email in set(emails):
            role = self._classify_role(email)
            score = 0
            
            # Company domain bonus
            if self._is_company_domain(email, site_host):
                score += 100
            
            # Editorial prefix scoring
            for weight, prefix in enumerate(reversed(self.EDITORIAL_PREFIXES), start=1):
                if email.startswith(prefix):
                    score += 45 + weight
                    break
            
            # Role scoring
            if role not in ("unknown", "general"):
                score += 10
                
            # Freemail penalty/bonus
            if self._is_freemail(email):
                score += -5 if role not in ("unknown", "general") else -40
            
            # General contact bonus
            if role == "general":
                score += 5
                
            # Context score
            score += context_score
            
            ranked.append((email, score, role))
        
        # Sort by score descending, then alphabetically
        ranked.sort(key=lambda x: (-x[1], x[0]))
        return ranked
    
    def _classify_role(self, email: str) -> str:
        """Classify email role (from original)"""
        email_lower = email.lower()
        
        # Check editorial prefixes
        for prefix in self.EDITORIAL_PREFIXES:
            if email_lower.startswith(prefix):
                return prefix.rstrip("@")
            if prefix.rstrip("@") in email_lower.split("@")[0]:
                return prefix.rstrip("@")
        
        # Check general contact patterns
        local = email_lower.split("@")[0]
        if any(k in local for k in ["info", "hello", "contact", "support", "team"]):
            return "general"
            
        return "unknown"
    
    def _is_company_domain(self, email: str, site_host: str) -> bool:
        """Check if email is from company domain (from original)"""
        email_host = email.split("@", 1)[-1] if "@" in email else ""
        return email_host.endswith(site_host) if email_host and site_host else False
    
    def _is_freemail(self, email: str) -> bool:
        """Check if email is from freemail provider (from original)"""
        email_host = email.split("@", 1)[-1] if "@" in email else ""
        return email_host in self.DISPOSABLE_HINTS
    
    def _verify_email_smtp_integrated(self, email: str) -> Dict[str, Any]:
        """Integrated SMTP verification (simplified from original)"""
        # Check cache first
        if email in self.smtp_cache:
            return self.smtp_cache[email]
        
        domain = email.split("@", 1)[-1] if "@" in email else ""
        
        # Basic validation
        if not domain or self._looks_like_asset_or_id(email):
            result = {'quality': 0, 'status': 'invalid', 'notes': 'bad_format'}
            self.smtp_cache[email] = result
            return result
        
        # MX lookup
        mx_hosts = self._resolve_mx(domain)
        if not mx_hosts:
            result = {'quality': 30, 'status': 'no_mx', 'notes': 'no_mx_records'}
            self.smtp_cache[email] = result
            return result
        
        # SMTP verification
        try:
            for mx_host in mx_hosts[:2]:  # Try first 2 MX records
                accepted, note, temp_fail = self._smtp_check_address(mx_host, email)
                
                if accepted:
                    result = {'quality': 85, 'status': 'deliverable', 'notes': f'mx={mx_host}; {note}'}
                    self.smtp_cache[email] = result
                    return result
                elif temp_fail:
                    result = {'quality': 70, 'status': 'temp_fail', 'notes': f'mx={mx_host}; {note}'}
                    self.smtp_cache[email] = result
                    return result
            
            # All failed
            result = {'quality': 40, 'status': 'rejected', 'notes': f'mx={",".join(mx_hosts[:3])}; all_failed'}
            self.smtp_cache[email] = result
            return result
            
        except Exception as e:
            result = {'quality': 55, 'status': 'unverifiable', 'notes': f'smtp_error: {str(e)}'}
            self.smtp_cache[email] = result
            return result
    
    def _resolve_mx(self, domain: str) -> List[str]:
        """Resolve MX records (simplified from original)"""
        if domain in self.mx_cache:
            return self.mx_cache[domain]
        
        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, 'MX', lifetime=self.SMTP_TIMEOUT)
            hosts = [str(r.exchange).rstrip('.') for r in sorted(answers, key=lambda r: r.preference)]
            self.mx_cache[domain] = hosts
            return hosts
        except:
            # Fallback to A record
            try:
                import dns.resolver
                dns.resolver.resolve(domain, 'A', lifetime=self.SMTP_TIMEOUT)
                hosts = [domain]
                self.mx_cache[domain] = hosts
                return hosts
            except:
                self.mx_cache[domain] = []
                return []
    
    def _smtp_check_address(self, mx_host: str, email: str) -> Tuple[bool, str, bool]:
        """SMTP address check (simplified from original)"""
        try:
            server = smtplib.SMTP(mx_host, 25, timeout=self.SMTP_TIMEOUT)
            server.set_debuglevel(0)
            
            # HELO/EHLO
            code, _ = server.ehlo(self.SMTP_HELO_DOMAIN)
            if not (200 <= code < 300):
                code, _ = server.helo(self.SMTP_HELO_DOMAIN)
            
            # STARTTLS if available
            try:
                if server.has_extn("starttls"):
                    server.starttls()
                    server.ehlo(self.SMTP_HELO_DOMAIN)
            except:
                pass
            
            # MAIL FROM
            code, _ = server.mail(self.SMTP_MAIL_FROM)
            if code >= 400:
                server.quit()
                return False, f"mailfrom_{code}", code in {421, 450, 451, 452}
            
            # RCPT TO
            code, msg = server.rcpt(email)
            accepted = code in (250, 251)
            note = f"rcpt_{code}"
            
            msg_str = str(msg).lower() if msg else ""
            temp_fail = (code in {421, 450, 451, 452}) or any(h in msg_str for h in 
                ["temporarily deferred", "try again later", "greylist", "rate limit"])
            
            server.quit()
            return accepted, note, temp_fail
            
        except (socket.timeout, smtplib.SMTPServerDisconnected):
            return False, "timeout", True
        except smtplib.SMTPConnectError:
            return False, "connect_fail", True
        except Exception as e:
            return False, f"smtp_error", True
    
    # Legacy compatibility methods for existing API
    def scrape_domain(self, domain: str) -> List[Dict[str, str]]:
        """Compatibility method - scrape domain and return simplified results"""
        if not domain.startswith(('http://', 'https://')):
            domain = f'https://{domain}'
        
        results = self.scrape_emails([domain], verify_emails=False)
        
        # Convert to legacy format
        legacy_results = []
        for item in results['verified_emails']:
            legacy_results.append({
                'email': item['email'],
                'name': '',  # Not extracted in new version
                'company': self._site_root(item['url']),
                'sources': 1,
                'source_details': [{'url': item['url'], 'method': 'integrated'}]
            })
        
        return legacy_results
    
    def scrape_multiple_domains(self, domains: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """Compatibility method - scrape multiple domains"""
        results = {}
        for domain in domains:
            try:
                results[domain] = self.scrape_domain(domain)
            except Exception:
                results[domain] = []
        return results