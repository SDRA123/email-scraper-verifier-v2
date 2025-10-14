import asyncio
import json
import time
from os import getenv
from typing import Dict, List, Any, Optional
from fastapi import WebSocket
from datetime import datetime
from urllib.parse import urlparse

from database import SessionLocal
from models import DataUpload, EmailData

class ProcessingPipeline:
    """
    Pipeline for processing emails through multiple steps:
    1. Blog Checker
    2. Email Scraper  
    3. Email Verifier
    With real-time progress tracking via WebSocket
    """
    @staticmethod
    def _concurrency_from_env(name: str, default: int) -> int:
        try:
            value = int(getenv(name, default))
            return value if value > 0 else default
        except (TypeError, ValueError):
            return default
    
    def __init__(self):
        self.active_processes: Dict[str, Dict] = {}
        self.websocket_connections: Dict[str, WebSocket] = {}
        # Optimized worker limits with race condition protections
        self._blog_concurrency = self._concurrency_from_env('PIPELINE_BLOG_WORKERS', 15)
        self._scrape_concurrency = self._concurrency_from_env('PIPELINE_SCRAPE_WORKERS', 12)
        self._verification_semaphore_limit = self._concurrency_from_env('PIPELINE_VERIFY_WORKERS', 25)
        self._blog_pool_semaphore: Optional[asyncio.Semaphore] = None
        self._scrape_pool_semaphore: Optional[asyncio.Semaphore] = None
        self._verification_pool_semaphore: Optional[asyncio.Semaphore] = None
        
    def _normalize_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            lower_keys = {str(key).lower(): value for key, value in record.items() if isinstance(key, str)}
            combined = {**record, **lower_keys}
            normalized.append(combined)
        return normalized

    @staticmethod
    def _prepare_url(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        url = str(value).strip()
        if not url:
            return None
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url

    def _extract_domain(self, value: Optional[str]) -> Optional[str]:
        url = self._prepare_url(value)
        if not url:
            return None
        try:
            parsed = urlparse(url)
            host = parsed.netloc or parsed.path
            return host.lower().lstrip('www.') if host else None
        except Exception:
            return value

    def _get_or_create_email_record(self, session, upload_id: int, email: str) -> EmailData:
        record = session.query(EmailData).filter(
            EmailData.upload_id == upload_id,
            EmailData.email == email
        ).first()
        if not record:
            record = EmailData(email=email, upload_id=upload_id)
            session.add(record)
        return record

    def _persist_chunk(self, process_id: str, step: str, chunk: List[Dict[str, Any]], upload_id: int):
        """Persist a chunk of results to the database"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            session = SessionLocal()
            try:
                # Get existing records for this upload
                existing_records = session.query(EmailData).filter(
                    EmailData.upload_id == upload_id
                ).all()
                
                # Create a map of normalized website -> record
                website_to_record = {}
                for rec in existing_records:
                    if rec.website:
                        normalized_website = self._extract_domain(rec.website)
                        if normalized_website and normalized_website not in website_to_record:
                            website_to_record[normalized_website] = rec
                
                # Process each item in the chunk
                for item in chunk:
                    if not isinstance(item, dict):
                        continue

                    website = item.get('website') or self._extract_domain(item.get('url') or item.get('domain'))
                    
                    if not website:
                        continue
                    
                    normalized_website = self._extract_domain(website)
                    record = website_to_record.get(normalized_website)
                    
                    if not record:
                        possible_websites = [
                            normalized_website,
                            f"https://{normalized_website}",
                            f"http://{normalized_website}",
                            f"www.{normalized_website}",
                            f"https://www.{normalized_website}"
                        ]
                        record = session.query(EmailData).filter(
                            EmailData.upload_id == upload_id,
                            EmailData.website.in_(possible_websites)
                        ).first()
                        
                        if not record:
                            record = EmailData(
                                upload_id=upload_id,
                                website=normalized_website,
                                source='pipeline',
                                email=item.get('email') or None
                            )
                            session.add(record)
                            session.flush()
                            website_to_record[normalized_website] = record

                    # Update blog info if this is blog_check step
                    if step == 'blog_check' and 'is_blog' in item:
                        record.is_blog = item.get('is_blog')
                        record.blog_score = item.get('blog_score')
                        indicators = None
                        if isinstance(item.get('blog_check'), dict):
                            indicators = item['blog_check'].get('blog_indicators')
                        indicators = indicators or item.get('blog_indicators')
                        if indicators:
                            record.blog_notes = ', '.join(indicators) if isinstance(indicators, list) else str(indicators)

                    # Update scraped email info if this is email_scrape step
                    if step == 'email_scrape':
                        scraped_emails = item.get('scraped_emails') or []
                        
                        if scraped_emails:
                            all_scraped = []
                            social_links_merged = {}
                            phone_numbers_merged = set()

                            for scraped in scraped_emails:
                                if isinstance(scraped, dict):
                                    scraped_email = scraped.get('email')
                                    if scraped_email:
                                        all_scraped.append(scraped)
                                        links = scraped.get('social_links', {})
                                        for key in ['linkedin', 'instagram', 'facebook', 'contact_form']:
                                            if links.get(key) and not social_links_merged.get(key):
                                                social_links_merged[key] = links[key]
                                        
                                        # Collect phone numbers
                                        phone_numbers = scraped.get('phone_numbers', [])
                                        if phone_numbers:
                                            phone_numbers_merged.update(phone_numbers)
                                else:
                                    scraped_email = scraped
                                    if scraped_email:
                                        all_scraped.append({'email': scraped_email})

                            if len(all_scraped) > 0:
                                primary = all_scraped[0]
                                record.email = primary.get('email')
                                if primary.get('role'):
                                    record.name = primary.get('role')
                                if 'verification' in primary and isinstance(primary['verification'], dict):
                                    verification = primary['verification']
                                    record.verification_quality = verification.get('quality')
                                    record.verification_status = verification.get('status')
                                    record.verification_notes = verification.get('notes')
                                    quality = verification.get('quality')
                                    if quality is not None:
                                        record.verified = quality >= 85

                            if len(all_scraped) > 1:
                                email_2 = all_scraped[1]
                                record.email_2 = email_2.get('email')
                                if 'verification' in email_2 and isinstance(email_2['verification'], dict):
                                    verification_2 = email_2['verification']
                                    record.email_2_quality = verification_2.get('quality')
                                    record.email_2_status = verification_2.get('status')
                                    record.email_2_notes = verification_2.get('notes')
                                    record.email_2_verified = verification_2.get('quality', 0) >= 85

                            if len(all_scraped) > 2:
                                email_3 = all_scraped[2]
                                record.email_3 = email_3.get('email')
                                if 'verification' in email_3 and isinstance(email_3['verification'], dict):
                                    verification_3 = email_3['verification']
                                    record.email_3_quality = verification_3.get('quality')
                                    record.email_3_status = verification_3.get('status')
                                    record.email_3_notes = verification_3.get('notes')
                                    record.email_3_verified = verification_3.get('quality', 0) >= 85

                            record.linkedin = social_links_merged.get('linkedin')
                            record.instagram = social_links_merged.get('instagram')
                            record.facebook = social_links_merged.get('facebook')
                            record.contact_form = social_links_merged.get('contact_form')
                            
                            # Save phone numbers (use the first/best phone number found)
                            if phone_numbers_merged:
                                # Convert to list and take the first phone number
                                phone_list = list(phone_numbers_merged)
                                record.phone = phone_list[0] if phone_list else None

                    # Update company and name if available (from any step)
                    if item.get('company') and not record.company:
                        record.company = item.get('company')
                    if item.get('name') and not record.name:
                        record.name = item.get('name')
                    if item.get('status') and not record.status:
                        record.status = item.get('status')
                    
                    # Update phone numbers from item-level data
                    if item.get('phone_numbers') and not record.phone:
                        phone_numbers = item.get('phone_numbers', [])
                        if phone_numbers:
                            record.phone = phone_numbers[0]  # Use the first phone number

                session.commit()
                return  # Success - exit retry loop
                
            except Exception as exc:
                session.rollback()
                error_msg = str(exc)
                if 'database is locked' in error_msg.lower() and attempt < max_retries - 1:
                    print(f"[pipeline] Database locked, retrying chunk ({attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"[pipeline] Failed to persist chunk for {step}: {exc}")
                    return
            finally:
                session.close()

    def _persist_step_results(self, process_id: str, step: str, data: List[Dict[str, Any]]):
        """Persist results with final data_json update"""
        process_state = self.active_processes.get(process_id)
        if not process_state:
            return

        upload_id = process_state.get('upload_id')
        if not upload_id:
            return

        # Update the data_json field with final results
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            session = SessionLocal()
            try:
                upload = session.query(DataUpload).filter(DataUpload.id == upload_id).first()
                if not upload:
                    return

                upload.data_json = json.dumps(data, default=str)
                upload.processed_count = len(data)
                session.add(upload)
                session.commit()
                return  # Success
                
            except Exception as exc:
                session.rollback()
                if 'database is locked' in str(exc).lower() and attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"[pipeline] Failed to update data_json for {step}: {exc}")
                    return
            finally:
                session.close()

    async def add_websocket(self, process_id: str, websocket: WebSocket):
        """Add WebSocket connection for real-time updates"""
        self.websocket_connections[process_id] = websocket
        
    async def remove_websocket(self, process_id: str):
        """Remove WebSocket connection"""
        if process_id in self.websocket_connections:
            del self.websocket_connections[process_id]
            
    async def send_progress(self, process_id: str, message: Dict[str, Any]):
        """Send progress update via WebSocket"""
        if process_id in self.websocket_connections:
            try:
                await self.websocket_connections[process_id].send_text(json.dumps(message))
            except:
                # Connection closed, remove it
                await self.remove_websocket(process_id)
                
    def is_process_running(self, process_id: str) -> bool:
        """Check if a process is currently running"""
        return process_id in self.active_processes and self.active_processes[process_id].get('status') == 'running'
        
    async def start_pipeline(
        self,
        process_id: str,
        data: List[Dict],
        steps: List[str],
        user_id: int,
        upload_id: Optional[int] = None
    ):
        """
        Start processing pipeline with specified steps
        Steps can be: 'blog_check', 'email_scrape', 'email_verify'
        """
        if self.is_process_running(process_id):
            await self.send_progress(process_id, {
                'type': 'error',
                'message': 'Process already running',
                'timestamp': datetime.now().isoformat()
            })
            return

        # Normalize step ordering and ensure verification follows scraping
        steps = steps or []
        ordered_steps: List[str] = []
        for step in steps:
            if step not in ordered_steps:
                ordered_steps.append(step)
        # Note: Removed auto-adding email_verify after email_scrape to prevent double verification
        steps = ordered_steps

        normalized_data = self._normalize_records(data)
            
        # Initialize process
        self.active_processes[process_id] = {
            'status': 'running',
            'current_step': '',
            'progress': 0,
            'total_items': len(normalized_data),
            'processed_items': 0,
            'results': {
                'blog_check': [],
                'email_scrape': [],
                'email_verify': []
            },
            'start_time': datetime.now(),
            'last_progress_time': datetime.now(),
            'user_id': user_id,
            'upload_id': upload_id
        }
        
        try:
            await self.send_progress(process_id, {
                'type': 'started',
                'message': f'Pipeline started with {len(steps)} steps',
                'steps': steps,
                'total_items': len(data),
                'timestamp': datetime.now().isoformat()
            })
            
            # Execute pipeline steps with overall timeout (2 hours max)
            pipeline_timeout = 2 * 60 * 60  # 2 hours
            
            async def run_pipeline_steps():
                current_data = normalized_data
                for step_index, step in enumerate(steps):
                    # Check if process was stopped
                    if self.active_processes.get(process_id, {}).get('status') != 'running':
                        return current_data
                        
                    await self.send_progress(process_id, {
                        'type': 'step_start',
                        'step': step,
                        'step_index': step_index + 1,
                        'total_steps': len(steps),
                        'message': f'Starting {step}...',
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    self.active_processes[process_id]['current_step'] = step
                    self.active_processes[process_id]['last_progress_time'] = datetime.now()
                    
                    if step == 'blog_check':
                        current_data = await self._run_blog_check(process_id, current_data)
                    elif step == 'email_scrape':
                        current_data = await self._run_email_scrape(process_id, current_data)
                    elif step == 'email_verify':
                        current_data = await self._run_email_verify(process_id, current_data)

                    await asyncio.to_thread(self._persist_step_results, process_id, step, current_data)
                        
                    await self.send_progress(process_id, {
                        'type': 'step_complete',
                        'step': step,
                        'step_index': step_index + 1,
                        'total_steps': len(steps),
                        'message': f'Completed {step}',
                        'timestamp': datetime.now().isoformat()
                    })
                    
                return current_data
            
            try:
                # Run pipeline with timeout
                await asyncio.wait_for(run_pipeline_steps(), timeout=pipeline_timeout)
                
                # Pipeline completed successfully
                self.active_processes[process_id]['status'] = 'completed'
                self.active_processes[process_id]['end_time'] = datetime.now()
                
                await self.send_progress(process_id, {
                    'type': 'completed',
                    'message': 'Pipeline completed successfully',
                    'results': self.active_processes[process_id]['results'],
                    'processing_time': (datetime.now() - self.active_processes[process_id]['start_time']).total_seconds(),
                    'timestamp': datetime.now().isoformat()
                })
                
            except asyncio.TimeoutError:
                self.active_processes[process_id]['status'] = 'timeout'
                self.active_processes[process_id]['error'] = 'Pipeline timeout after 2 hours'
                
                await self.send_progress(process_id, {
                    'type': 'timeout',
                    'message': 'Pipeline timed out after 2 hours. Partial results may be available.',
                    'timestamp': datetime.now().isoformat()
                })
            
        except Exception as e:
            self.active_processes[process_id]['status'] = 'failed'
            self.active_processes[process_id]['error'] = str(e)
            
            await self.send_progress(process_id, {
                'type': 'error',
                'message': f'Pipeline failed: {str(e)}',
                'timestamp': datetime.now().isoformat()
            })
        finally:
            # Clean up semaphores to prevent memory leaks
            if process_id in self.active_processes:
                if self.active_processes[process_id].get('status') in ['completed', 'failed', 'timeout', 'stopped']:
                    # Keep record for history but mark as finished
                    self.active_processes[process_id]['finished'] = True
            
    async def _run_blog_check(self, process_id: str, data: List[Dict]) -> List[Dict]:
        """Run blog checking step with chunked database updates"""
        from email_services import BlogChecker

        blog_checker = BlogChecker()
        total_items = len(data) or 1
        if self._blog_pool_semaphore is None:
            self._blog_pool_semaphore = asyncio.Semaphore(self._blog_concurrency)
        pool = self._blog_pool_semaphore
        progress_lock = asyncio.Lock()
        processed = 0
        
        # Chunked update configuration
        chunk_size = 25
        results_chunk = []
        upload_id = self.active_processes[process_id].get('upload_id')

        async def process_item(index: int, item: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal processed
            prepared_url = self._prepare_url(item.get('url') or item.get('domain') or item.get('website', ''))
            if prepared_url:
                async with pool:
                    domain = self._extract_domain(prepared_url)
                    if domain:
                        item['website'] = domain
                    item['url'] = prepared_url

                    try:
                        # Add timeout for individual blog checking operations (2 minutes max per site)
                        blog_result = await asyncio.wait_for(
                            asyncio.to_thread(blog_checker.check_single_url, prepared_url),
                            timeout=120  # 2 minutes per site
                        )
                        item['blog_check'] = blog_result
                        item['is_blog'] = blog_result.get('is_blog', False)
                        item['blog_score'] = blog_result.get('blog_score', 0)
                        item['blog_indicators'] = blog_result.get('blog_indicators', [])
                        item['recent_reason'] = blog_result.get('recent_reason')
                    except asyncio.TimeoutError:
                        item['blog_check'] = {'is_blog': False, 'blog_score': 0, 'error': 'timeout_after_120_seconds'}
                        item['is_blog'] = False
                        item['blog_score'] = 0
                        item['blog_indicators'] = []
                    except Exception as exc:
                        item['blog_check'] = {'is_blog': False, 'blog_score': 0, 'error': str(exc)}
                        item['is_blog'] = False
                        item['blog_score'] = 0
                        item['blog_indicators'] = []

            current_item = item.get('website') or prepared_url

            async with progress_lock:
                processed += 1
                current_processed = processed
                current_progress = int(current_processed / total_items * 100)
                self.active_processes[process_id]['processed_items'] = current_processed
                self.active_processes[process_id]['progress'] = current_progress

            await self.send_progress(process_id, {
                'type': 'progress',
                'step': 'blog_check',
                'progress': current_progress,
                'processed': current_processed,
                'total': total_items,
                'current_item': current_item,
                'timestamp': datetime.now().isoformat()
            })

            return item

        # Use asyncio.gather with timeout to prevent indefinite hangs
        all_results = []
        
        try:
            # Process tasks with timeout (20 minutes max)
            timeout = 20 * 60  # 20 minutes
            tasks = [asyncio.create_task(process_item(index, item)) for index, item in enumerate(data)]
            
            # Process tasks in batches to avoid overwhelming system
            batch_size = 25
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                
                try:
                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*batch, return_exceptions=True),
                        timeout=timeout
                    )
                    
                    for result in batch_results:
                        if isinstance(result, Exception):
                            print(f"[pipeline] Task failed in blog_check: {result}")
                            continue
                        
                        all_results.append(result)
                        results_chunk.append(result)
                        
                        # Persist chunk when it reaches the chunk size
                        if len(results_chunk) >= chunk_size:
                            await asyncio.to_thread(
                                self._persist_chunk,
                                process_id,
                                'blog_check',
                                results_chunk.copy(),
                                upload_id
                            )
                            results_chunk.clear()
                            
                except asyncio.TimeoutError:
                    print(f"[pipeline] Batch timeout in blog_check, continuing with next batch")
                    continue
                    
        except Exception as e:
            print(f"[pipeline] Error in blog_check processing: {e}")
        
        # Persist any remaining items in the final chunk
        if results_chunk:
            await asyncio.to_thread(
                self._persist_chunk,
                process_id,
                'blog_check',
                results_chunk,
                upload_id
            )
        
        self.active_processes[process_id]['results']['blog_check'] = all_results
        return all_results
        
    async def _run_email_scrape(self, process_id: str, data: List[Dict]) -> List[Dict]:
        """Run email scraping step with chunked database updates"""
        from email_services import EmailScraper
        
        scraper = EmailScraper()
        total_items = len(data) or 1
        if self._scrape_pool_semaphore is None:
            self._scrape_pool_semaphore = asyncio.Semaphore(self._scrape_concurrency)
        pool = self._scrape_pool_semaphore
        progress_lock = asyncio.Lock()
        processed = 0
        
        # Chunked update configuration
        chunk_size = 25
        results_chunk = []
        upload_id = self.active_processes[process_id].get('upload_id')

        async def process_item(index: int, item: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal processed
            raw_url = item.get('url') or item.get('domain') or item.get('website', '')
            prepared_url = self._prepare_url(raw_url)
            if prepared_url:
                async with pool:
                    domain = self._extract_domain(prepared_url)
                    if domain:
                        item['website'] = domain
                    item['url'] = prepared_url

                    try:
                        # Add timeout for individual scraping operations (5 minutes max per site)
                        scrape_results = await asyncio.wait_for(
                            asyncio.to_thread(scraper.scrape_emails, [prepared_url], True),
                            timeout=300  # 5 minutes per site
                        )
                        item['scraped_emails'] = scrape_results.get('verified_emails', [])
                        item['scrape_metadata'] = scrape_results.get('metadata', {})
                        item['failed_urls'] = scrape_results.get('failed_urls', [])
                    except asyncio.TimeoutError:
                        item['scraped_emails'] = []
                        item['scrape_error'] = f'timeout_after_300_seconds'
                    except Exception as exc:
                        item['scraped_emails'] = []
                        item['scrape_error'] = str(exc)

            current_item = item.get('website') or prepared_url

            async with progress_lock:
                processed += 1
                current_processed = processed
                current_progress = int(current_processed / total_items * 100)
                self.active_processes[process_id]['processed_items'] = current_processed
                self.active_processes[process_id]['progress'] = current_progress

            await self.send_progress(process_id, {
                'type': 'progress',
                'step': 'email_scrape',
                'progress': current_progress,
                'processed': current_processed,
                'total': total_items,
                'current_item': current_item,
                'timestamp': datetime.now().isoformat()
            })

            return item

        # Use asyncio.gather with timeout to prevent indefinite hangs
        all_results = []
        
        try:
            # Process tasks with timeout (30 minutes max)
            timeout = 30 * 60  # 30 minutes
            tasks = [asyncio.create_task(process_item(index, item)) for index, item in enumerate(data)]
            
            # Process tasks in batches to avoid overwhelming system
            batch_size = 20
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                
                try:
                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*batch, return_exceptions=True),
                        timeout=timeout
                    )
                    
                    for result in batch_results:
                        if isinstance(result, Exception):
                            print(f"[pipeline] Task failed in email_scrape: {result}")
                            continue
                        
                        all_results.append(result)
                        results_chunk.append(result)
                        
                        # Persist chunk when it reaches the chunk size
                        if len(results_chunk) >= chunk_size:
                            await asyncio.to_thread(
                                self._persist_chunk,
                                process_id,
                                'email_scrape',
                                results_chunk.copy(),
                                upload_id
                            )
                            results_chunk.clear()
                            
                except asyncio.TimeoutError:
                    print(f"[pipeline] Batch timeout in email_scrape, continuing with next batch")
                    continue
                    
        except Exception as e:
            print(f"[pipeline] Error in email_scrape processing: {e}")
        
        # Persist any remaining items in the final chunk
        if results_chunk:
            await asyncio.to_thread(
                self._persist_chunk,
                process_id,
                'email_scrape',
                results_chunk,
                upload_id
            )
        
        self.active_processes[process_id]['results']['email_scrape'] = all_results
        return all_results
        
    async def _run_email_verify(self, process_id: str, data: List[Dict]) -> List[Dict]:
        """Run email verification step with chunked database updates"""
        from email_services import EmailVerifier

        verifier = EmailVerifier()
        results: List[Dict[str, Any]] = []
        
        # Chunked update configuration
        chunk_size = 25
        upload_id = self.active_processes[process_id].get('upload_id')

        # Collect all emails to verify, normalized and deduplicated
        unique_emails_set = set()
        for item in data:
            if 'scraped_emails' in item:
                for email_entry in item['scraped_emails']:
                    if isinstance(email_entry, dict):
                        raw_email = email_entry.get('email')
                    else:
                        raw_email = email_entry
                    normalized_email = verifier.normalize_email(raw_email) if raw_email else None
                    if normalized_email:
                        unique_emails_set.add(normalized_email)
            if item.get('email'):
                normalized_email = verifier.normalize_email(item['email'])
                if normalized_email:
                    unique_emails_set.add(normalized_email)

        unique_emails = list(unique_emails_set)

        if not unique_emails:
            self.active_processes[process_id]['results']['email_verify'] = data
            return data

        if self._verification_pool_semaphore is None:
            self._verification_pool_semaphore = asyncio.Semaphore(self._verification_semaphore_limit)
        pool = self._verification_pool_semaphore
        verified_results: Dict[str, Dict[str, Any]] = {}
        total_emails = len(unique_emails)
        completed = 0
        
        # Track items processed for chunked updates
        items_processed_count = 0
        results_chunk = []

        async def verify_email(email: str) -> tuple[str, Dict[str, Any]]:
            async with pool:
                try:
                    # Add timeout for individual email verification (60 seconds max per email)
                    result = await asyncio.wait_for(
                        asyncio.to_thread(verifier.verify_email_advanced, email),
                        timeout=60  # 1 minute per email
                    )
                except asyncio.TimeoutError:
                    result = {
                        'email': email,
                        'valid': False,
                        'quality': 0,
                        'status': 'timeout',
                        'notes': 'verification_timeout_after_60_seconds'
                    }
                except Exception as exc:
                    result = {
                        'email': email,
                        'valid': False,
                        'quality': 0,
                        'status': 'error',
                        'notes': f'verification_error: {exc}'
                    }
                else:
                    if not result.get('email'):
                        result['email'] = email
                return email, result

        # Use asyncio.gather with timeout to prevent indefinite hangs
        try:
            # Process tasks with timeout (15 minutes max)
            timeout = 15 * 60  # 15 minutes
            tasks = [asyncio.create_task(verify_email(email)) for email in unique_emails]
            
            # Process tasks in batches
            batch_size = 30
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                
                try:
                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*batch, return_exceptions=True),
                        timeout=timeout
                    )
                    
                    for result in batch_results:
                        if isinstance(result, Exception):
                            print(f"[pipeline] Task failed in email_verify: {result}")
                            continue
                            
                        email, verification = result
                        verified_results[email] = verification
                        completed += 1
                        progress = int(completed / total_emails * 100) if total_emails else 100
                        self.active_processes[process_id]['processed_items'] = completed
                        self.active_processes[process_id]['progress'] = progress

                        await self.send_progress(process_id, {
                            'type': 'progress',
                            'step': 'email_verify',
                            'progress': progress,
                            'processed': completed,
                            'total': total_emails,
                            'current_item': email,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                except asyncio.TimeoutError:
                    print(f"[pipeline] Batch timeout in email_verify, continuing with next batch")
                    continue
                    
        except Exception as e:
            print(f"[pipeline] Error in email_verify processing: {e}")

        # Apply verification results to data and persist in chunks
        for item in data:
            candidates: List[Dict[str, Any]] = []

            scraped_list = item.get('scraped_emails', []) or []
            enriched_scraped = []
            for email_entry in scraped_list:
                if isinstance(email_entry, dict):
                    email_value = email_entry.get('email')
                    display_entry = dict(email_entry)
                else:
                    email_value = email_entry
                    display_entry = {'email': email_entry}

                normalized_email = verifier.normalize_email(email_value) if email_value else None
                if normalized_email and normalized_email in verified_results:
                    verification = verified_results[normalized_email]
                    display_entry['email'] = normalized_email
                    display_entry['verification'] = verification
                    display_entry['verified'] = verification.get('valid')
                    display_entry['status'] = verification.get('status')
                    candidates.append(verification)
                enriched_scraped.append(display_entry)

            if enriched_scraped:
                item['scraped_emails'] = enriched_scraped

            if item.get('email'):
                normalized_primary = verifier.normalize_email(item['email'])
                if normalized_primary in verified_results:
                    verification = verified_results[normalized_primary]
                    item['email'] = normalized_primary
                    item['verification'] = verification
                    item['verified'] = verification.get('valid')
                    item['status'] = verification.get('status')
                    candidates.append(verification)

            # Determine best email candidate based on validity and quality
            if candidates:
                sorted_candidates = sorted(
                    candidates,
                    key=lambda entry: (
                        1 if entry.get('valid') else 0,
                        entry.get('quality') or 0
                    ),
                    reverse=True
                )
                best = sorted_candidates[0]
                item['best_email'] = {
                    'email': best.get('email'),
                    'quality': best.get('quality'),
                    'status': best.get('status'),
                    'notes': best.get('notes'),
                    'valid': best.get('valid')
                }

            results.append(item)
            results_chunk.append(item)
            items_processed_count += 1
            
            # Persist chunk when it reaches the chunk size
            if len(results_chunk) >= chunk_size:
                await asyncio.to_thread(
                    self._persist_chunk,
                    process_id,
                    'email_verify',
                    results_chunk.copy(),
                    upload_id
                )
                results_chunk.clear()
        
        # Persist any remaining items in the final chunk
        if results_chunk:
            await asyncio.to_thread(
                self._persist_chunk,
                process_id,
                'email_verify',
                results_chunk,
                upload_id
            )
            
        self.active_processes[process_id]['results']['email_verify'] = results
        return results
        
    def get_process_status(self, process_id: str) -> Dict[str, Any]:
        """Get current status of a process"""
        return self.active_processes.get(process_id, {'status': 'not_found'})
        
    def get_all_processes(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all processes for a user"""
        user_processes = []
        for pid, process in self.active_processes.items():
            if process.get('user_id') == user_id:
                process_info = process.copy()
                process_info['process_id'] = pid
                user_processes.append(process_info)
        return user_processes

# Global pipeline manager
pipeline_manager = ProcessingPipeline()