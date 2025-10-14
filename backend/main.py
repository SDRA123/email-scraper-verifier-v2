from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form, WebSocket, WebSocketDisconnect, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func, or_
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
from pathlib import Path
import pandas as pd
import json
import io
import uuid
import asyncio
from datetime import datetime, timedelta
import re

from database import SessionLocal, engine, Base
from models import User, EmailData, DataUpload
from auth import verify_password, get_password_hash, create_access_token, verify_token
from email_services import EmailVerifier, EmailScraper, BlogChecker
from schemas import UserCreate, UserResponse, Token, EmailDataResponse, VerificationResult
from duplicate_remover import remove_duplicate_websites, remove_duplicate_emails_in_record, find_or_create_record_by_website
from pipeline import pipeline_manager

# Create tables
Base.metadata.create_all(bind=engine)


def ensure_email_data_columns():
    """Ensure newly added columns exist in the email_data table (SQLite)."""
    with engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(email_data)"))
        }

        def add_column(name: str, ddl: str):
            if name not in existing_columns:
                connection.execute(text(f"ALTER TABLE email_data ADD COLUMN {name} {ddl}"))
                existing_columns.add(name)

        # Original columns
        add_column("website", "VARCHAR")
        add_column("is_blog", "BOOLEAN")
        add_column("blog_score", "INTEGER")
        add_column("blog_notes", "TEXT")
        add_column("verification_quality", "INTEGER")
        add_column("verification_status", "TEXT")
        add_column("verification_notes", "TEXT")
        add_column("source", "VARCHAR")

        # Multiple emails support
        add_column("email_2", "VARCHAR")
        add_column("email_3", "VARCHAR")
        add_column("email_2_verified", "BOOLEAN")
        add_column("email_3_verified", "BOOLEAN")
        add_column("email_2_quality", "INTEGER")
        add_column("email_3_quality", "INTEGER")
        add_column("email_2_status", "VARCHAR")
        add_column("email_2_notes", "TEXT")
        add_column("email_3_status", "VARCHAR")
        add_column("email_3_notes", "TEXT")

        # Social and contact links
        add_column("linkedin", "VARCHAR")
        add_column("instagram", "VARCHAR")
        add_column("facebook", "VARCHAR")
        add_column("contact_form", "VARCHAR")

        # Email campaign tracking
        add_column("email_sent", "BOOLEAN")
        add_column("email_sent_date", "DATETIME")

        # Additional metadata
        add_column("phone", "VARCHAR")
        add_column("job_title", "VARCHAR")
        add_column("notes", "TEXT")


ensure_email_data_columns()


def ensure_admin_user():
    """Ensure admin user exists"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            from auth import get_password_hash
            admin = User(
                username="admin",
                email="admin@admin.com",
                hashed_password=get_password_hash("admin"),
                is_admin=True,
                is_active=True
            )
            db.add(admin)
            db.commit()
            print("✅ Admin user created (username: admin, password: admin)")
        else:
            if not admin.is_admin:
                admin.is_admin = True
                db.commit()
                print("✅ Admin user permissions updated")
    except Exception as e:
        print(f"⚠️  Admin user initialization error: {e}")
        db.rollback()
    finally:
        db.close()


ensure_admin_user()

app = FastAPI(title="Email Verifier and Scraper API", version="1.0.0")

_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: Optional[str], fallback: str) -> str:
    base = (name or '').strip()
    if not base:
        base = fallback
    sanitized = _FILENAME_SANITIZER.sub('_', base)
    sanitized = sanitized.strip('._')
    return sanitized or fallback

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000", 
        "http://192.168.18.14:3000",
        "http://0.0.0.0:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Email Verifier and Scraper API", 
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "authentication": "/api/auth/login",
            "email_verification": "/api/email/verify",
            "email_scraping": "/api/email/scrape",
            "blog_checking": "/api/blog/check"
        }
    }

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get current user
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    print(f"[DEBUG] get_current_user called with token: {token[:20]}..." if token else "No token provided")
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        print("[DEBUG] No token provided")
        raise credentials_exception
    
    username = verify_token(token)
    print(f"[DEBUG] Token verification result - username: {username}")
    
    if username is None:
        print("[DEBUG] Token verification failed - invalid token")
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    print(f"[DEBUG] Database query result - user found: {user is not None}")
    
    if user is None:
        print(f"[DEBUG] User not found in database for username: {username}")
        raise credentials_exception
    
    print(f"[DEBUG] Authentication successful for user: {user.username}")
    return user

# Dependency to check admin privileges
async def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

# Authentication routes
@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user"
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "is_admin": user.is_admin,
            "created_at": user.created_at
        }
    }

@app.post("/api/auth/register", response_model=UserResponse)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if username exists
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    # Check if email exists
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@app.get("/api/auth/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# User management routes (admin only)
@app.get("/api/users/", response_model=List[UserResponse])
async def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), admin_user: User = Depends(get_admin_user)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@app.post("/api/users/", response_model=UserResponse)
async def create_user(user: UserCreate, db: Session = Depends(get_db), admin_user: User = Depends(get_admin_user)):
    # Check if username exists
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        is_admin=getattr(user, 'is_admin', False),
        is_active=getattr(user, 'is_active', True)
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@app.put("/api/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_update: dict, db: Session = Depends(get_db), admin_user: User = Depends(get_admin_user)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    for key, value in user_update.items():
        if hasattr(db_user, key) and key != 'id':
            setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), admin_user: User = Depends(get_admin_user)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted successfully"}

# Email processing routes
@app.post("/api/email/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload Excel or CSV file for processing"""
    allowed_extensions = ('.xlsx', '.xls', '.csv', '.tsv', '.txt')
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(allowed_extensions)} files are allowed"
        )

    try:
        # Read file based on type
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(file.file)
        elif file.filename.lower().endswith('.tsv') or file.filename.lower().endswith('.txt'):
            df = pd.read_csv(file.file, sep='\t')
        else:
            df = pd.read_excel(file.file)

        # Convert to JSON
        data_json = df.to_json(orient='records')

        # Store in database
        upload_record = DataUpload(
            filename=file.filename,
            user_id=current_user.id,
            data_json=data_json,
            processed_count=len(df)
        )
        db.add(upload_record)
        db.commit()
        db.refresh(upload_record)

        def normalize_cell(value):
            if pd.isna(value):
                return ''
            if isinstance(value, str):
                return value.strip()
            return value

        # Process individual email records with duplicate checking
        for _, row in df.iterrows():
            row_map = {str(col).lower(): normalize_cell(row[col]) for col in df.columns}
            email_value = row_map.get('email') or row_map.get('email address') or ''
            name_value = row_map.get('name') or row_map.get('full name') or ''
            company_value = row_map.get('company') or row_map.get('organisation') or row_map.get('organization') or ''
            website_value = row_map.get('website') or row_map.get('url') or row_map.get('domain') or ''

            # Normalize website
            if website_value and not website_value.startswith('http'):
                website_value = f'https://{website_value}'

            # Check if record exists for this website
            existing_record = find_or_create_record_by_website(db, website_value, upload_record.id)

            if existing_record:
                # Update existing record with new email if different
                if email_value and email_value != existing_record.email:
                    if not existing_record.email_2:
                        existing_record.email_2 = email_value
                    elif not existing_record.email_3 and email_value != existing_record.email_2:
                        existing_record.email_3 = email_value
                # Update other fields if not set
                if not existing_record.company and company_value:
                    existing_record.company = company_value
                if not existing_record.name and name_value:
                    existing_record.name = name_value
            else:
                # Create new record
                email_record = EmailData(
                    email=email_value,
                    name=name_value,
                    company=company_value,
                    website=website_value,
                    status='Unverified',
                    source='upload',
                    upload_id=upload_record.id
                )
                db.add(email_record)

        db.commit()

        # Remove any duplicates that might have been created
        remove_duplicate_websites(db, upload_record.id)

        return {
            "message": "File uploaded successfully",
            "data_id": upload_record.id,
            "processed_count": len(df)
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

@app.post("/api/email/verify/{data_id}")
async def verify_emails(
    data_id: int,
    request_body: dict = None,
    enable_smtp: bool = True,
    max_workers: int = 8,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify emails for a given upload.
    If request_body contains 'emails' array, only verify those specific emails.
    Otherwise, verify all emails in the upload.
    """
    # Parse request body if provided
    emails_filter = None
    if request_body:
        emails_filter = request_body.get('emails', None)
    
    # Get email records
    query = db.query(EmailData).filter(EmailData.upload_id == data_id)
    
    # If specific emails are requested, filter by them
    if emails_filter:
        query = query.filter(EmailData.email.in_(emails_filter))
    
    email_records = query.all()
    
    if not email_records:
        raise HTTPException(status_code=404, detail="No email data found")
    
    # Use enhanced verifier with configuration
    verifier = EmailVerifier(enable_smtp=enable_smtp, max_workers=max_workers)
    
    # Collect unique emails for bulk verification
    emails_to_verify = [record.email for record in email_records if record.email]

    if not emails_to_verify:
        raise HTTPException(status_code=400, detail="No valid emails to verify")

    # Perform bulk verification
    verification_results = verifier.verify_bulk(emails_to_verify)

    # Create a mapping using normalized email keys
    results_map = {result['email']: result for result in verification_results if result.get('email')}

    results = []
    for record in email_records:
        normalized_email = verifier.normalize_email(record.email) if record.email else None
        if not normalized_email:
            continue

        if normalized_email in results_map:
            details = results_map[normalized_email]
            record.email = normalized_email
            record.verified = bool(details.get('valid'))
            record.verification_quality = details.get('quality')
            record.verification_status = details.get('status')
            record.verification_notes = details.get('notes')
            record.status = details.get('status') or ("Verified" if record.verified else "Invalid")

            results.append({
                "email": normalized_email,
                "is_valid": record.verified,
                "quality": details.get('quality'),
                "status": details.get('status'),
                "notes": details.get('notes')
            })
    
    db.commit()
    
    return {
        "verified_count": len(results),
        "total_requested": len(emails_to_verify),
        "results": results
    }

@app.post("/api/email/verify-single")
async def verify_single_email(
    email_data: dict,
    current_user: User = Depends(get_current_user)
):
    email = email_data.get("email", "")
    enable_smtp = email_data.get("enable_smtp", True)
    
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    verifier = EmailVerifier(enable_smtp=enable_smtp)
    details = verifier.verify_email_advanced(email)
    
    return {
        "email": details.get("email", email),
        "is_valid": details.get("valid"),
        "quality": details.get("quality"),
        "status": details.get("status"),
        "notes": details.get("notes")
    }

@app.post("/api/blog/check")
async def check_blog_presence(
    urls_data: dict,
    current_user: User = Depends(get_current_user)
):
    urls = urls_data.get("urls", [])
    max_workers = urls_data.get("max_workers", 8)
    
    if not urls:
        raise HTTPException(status_code=400, detail="URLs list is required")
    
    blog_checker = BlogChecker(max_workers=max_workers)
    results = blog_checker.check_multiple_urls(urls)
    
    return {
        "total_checked": len(results),
        "blogs_found": sum(1 for r in results if r['is_blog']),
        "recent_content_found": sum(1 for r in results if r['has_recent_content']),
        "results": results
    }

@app.post("/api/blog/check-single")
async def check_single_blog(
    blog_data: dict,
    current_user: User = Depends(get_current_user)
):
    url = blog_data.get("url", "")
    
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    blog_checker = BlogChecker()
    result = blog_checker.check_single_url(url)
    
    return result

@app.post("/api/blog/check-upload/{data_id}")
async def check_blogs_for_upload(
    data_id: int,
    request_body: dict = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check blog status for websites in an upload.
    If request_body contains 'websites' array, only check those specific websites.
    Otherwise, check all websites in the upload.
    """
    # Parse request body if provided
    websites_filter = None
    if request_body:
        websites_filter = request_body.get('websites', None)
    
    # Get email records
    query = db.query(EmailData).filter(EmailData.upload_id == data_id)
    
    # If specific websites are requested, filter by them
    if websites_filter:
        query = query.filter(EmailData.website.in_(websites_filter))
    
    email_records = query.all()
    
    if not email_records:
        raise HTTPException(status_code=404, detail="No email data found")
    
    # Collect unique websites (normalized)
    website_map = {}
    for record in email_records:
        if record.website:
            normalized_website = record.website.lower().strip()
            if normalized_website not in website_map:
                website_map[normalized_website] = []
            website_map[normalized_website].append(record)
    
    if not website_map:
        raise HTTPException(status_code=400, detail="No websites found in upload data")
    
    websites = list(website_map.keys())
    
    # Check blogs
    blog_checker = BlogChecker()
    results = blog_checker.check_multiple_urls(websites)
    
    # Create a mapping of normalized website to blog results
    blog_map = {}
    for result in results:
        url = result.get('url', '').lower().strip()
        blog_map[url] = result
    
    # Update database records
    updated_count = 0
    for website, records in website_map.items():
        if website in blog_map:
            blog_result = blog_map[website]
            
            # Update ALL records for this website
            for record in records:
                record.is_blog = blog_result.get('is_blog', False)
                record.blog_score = blog_result.get('blog_score', 0)
                
                # Compile blog notes
                notes_parts = []
                if blog_result.get('has_recent_content'):
                    notes_parts.append(f"Recent: {blog_result.get('recent_reason', 'Yes')}")
                if blog_result.get('blog_indicators'):
                    indicators = blog_result['blog_indicators']
                    if isinstance(indicators, list):
                        notes_parts.append(f"Indicators: {', '.join(indicators[:3])}")
                
                record.blog_notes = '; '.join(notes_parts) if notes_parts else None
                updated_count += 1
    
    db.commit()
    
    return {
        "total_websites": len(websites),
        "websites_checked": len(websites),
        "blogs_found": sum(1 for r in results if r.get('is_blog')),
        "recent_content_found": sum(1 for r in results if r.get('has_recent_content')),
        "updated_records": updated_count
    }

@app.post("/api/email/scrape")
async def scrape_emails(
    domain_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    domain = domain_data.get("domain", "")
    verify_emails = domain_data.get("verify_emails", True)

    if not domain:
        raise HTTPException(status_code=400, detail="Domain is required")

    try:
        # Use new integrated EmailScraper with verification
        scraper = EmailScraper()

        # Ensure domain has protocol
        if not domain.startswith(('http://', 'https://')):
            domain_url = f'https://{domain}'
        else:
            domain_url = domain

        # Scrape up to 3 emails with integrated verification and social links
        results = scraper.scrape_emails([domain_url], verify_emails=verify_emails, max_emails_per_site=3)

        # Create upload record for scraped data
        upload_record = DataUpload(
            filename=f"scraped_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            user_id=current_user.id,
            data_json=json.dumps(results),
            processed_count=len(results['verified_emails'])
        )
        db.add(upload_record)
        db.commit()
        db.refresh(upload_record)

        # Store scraped emails with enhanced metadata (up to 3 emails per entry)
        # Group emails by social links (same website)
        emails_by_site = {}
        for email_info in results['verified_emails']:
            site_key = email_info.get('url', domain_url)
            if site_key not in emails_by_site:
                emails_by_site[site_key] = []
            emails_by_site[site_key].append(email_info)

        for site_url, email_list in emails_by_site.items():
            # Take up to 3 emails for this site
            email_1 = email_list[0] if len(email_list) > 0 else None
            email_2 = email_list[1] if len(email_list) > 1 else None
            email_3 = email_list[2] if len(email_list) > 2 else None

            # Get social links from first email (they're the same for all emails from same site)
            social_links = email_1.get('social_links', {}) if email_1 else {}

            email_record = EmailData(
                # Primary email
                email=email_1.get('email', '') if email_1 else '',
                name=email_1.get('role', '') if email_1 else '',
                company=domain,
                website=site_url,
                upload_id=upload_record.id,
                verification_quality=email_1.get('verification', {}).get('quality', 0) if email_1 else 0,
                verification_status=email_1.get('verification', {}).get('status', '') if email_1 else '',
                verification_notes=email_1.get('verification', {}).get('notes', '') if email_1 else '',
                verified=email_1.get('verification', {}).get('quality', 0) >= 70 if email_1 else False,
                status=email_1.get('verification', {}).get('status', '') if email_1 else '',
                source='scrape',
                # Additional emails
                email_2=email_2.get('email', '') if email_2 else None,
                email_2_verified=email_2.get('verification', {}).get('quality', 0) >= 70 if email_2 else None,
                email_2_quality=email_2.get('verification', {}).get('quality', 0) if email_2 else None,
                email_3=email_3.get('email', '') if email_3 else None,
                email_3_verified=email_3.get('verification', {}).get('quality', 0) >= 70 if email_3 else None,
                email_3_quality=email_3.get('verification', {}).get('quality', 0) if email_3 else None,
                # Social links
                linkedin=social_links.get('linkedin'),
                instagram=social_links.get('instagram'),
                facebook=social_links.get('facebook'),
                contact_form=social_links.get('contact_form')
            )
            db.add(email_record)

        db.commit()

        return {
            "domain": domain,
            "total_emails": len(results['verified_emails']),
            "scraped_emails": len(results['scraped_emails']),
            "failed_urls": len(results['failed_urls']),
            "data_id": upload_record.id,
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error scraping domain: {str(e)}")

@app.post("/api/email/scrape-multiple")
async def scrape_multiple_domains(
    domains_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    domains = domains_data.get("domains", [])
    verify_emails = domains_data.get("verify_emails", True)
    
    if not domains:
        raise HTTPException(status_code=400, detail="Domains list is required")
    
    try:
        # Use new integrated EmailScraper
        scraper = EmailScraper()
        
        # Prepare URLs with protocols
        domain_urls = []
        for domain in domains:
            if not domain.startswith(('http://', 'https://')):
                domain_urls.append(f'https://{domain}')
            else:
                domain_urls.append(domain)
        
        # Scrape all domains with integrated verification
        results = scraper.scrape_emails(domain_urls, verify_emails=verify_emails)
        
        # Create upload record for all scraped data
        upload_record = DataUpload(
            filename=f"multi_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            user_id=current_user.id,
            data_json=json.dumps(results),
            processed_count=len(results['verified_emails'])
        )
        db.add(upload_record)
        db.commit()
        db.refresh(upload_record)
        
        # Store all scraped and verified emails
        total_emails = 0
        for email_info in results['verified_emails']:
            # Extract domain from URL
            domain = scraper._site_root(email_info.get('url', ''))
            
            email_record = EmailData(
                email=email_info.get('email', ''),
                name=email_info.get('role', ''),
                company=domain,
                website=email_info.get('url') or domain,
                upload_id=upload_record.id,
                verification_quality=email_info.get('verification', {}).get('quality', 0),
                verification_status=email_info.get('verification', {}).get('status', ''),
                verification_notes=email_info.get('verification', {}).get('notes', ''),
                verified=email_info.get('verification', {}).get('quality', 0) >= 70,
                status=email_info.get('verification', {}).get('status', ''),
                source='scrape'
            )
            db.add(email_record)
            total_emails += 1
        
        db.commit()
        
        return {
            "domains_processed": len(domains),
            "total_emails": total_emails,
            "scraped_emails": len(results['scraped_emails']),
            "failed_urls": len(results['failed_urls']),
            "data_id": upload_record.id,
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error scraping domains: {str(e)}")

@app.get("/api/email/data")
async def get_all_email_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all email data for the current user across all uploads"""
    # Get all uploads for the user
    user_uploads = db.query(DataUpload).filter(
        DataUpload.user_id == current_user.id
    ).all()

    if not user_uploads:
        return []

    upload_ids = [upload.id for upload in user_uploads]

    # Get all email records for these uploads
    email_records = db.query(EmailData).filter(
        EmailData.upload_id.in_(upload_ids)
    ).order_by(EmailData.created_at.desc()).all()

    return [
        {
            "row_id": record.id,
            "id": record.id,
            "email": record.email,
            "name": record.name,
            "company": record.company,
            "website": record.website,
            "verified": bool(record.verification_quality and record.verification_quality >= 85) or bool(record.verified),
            "status": record.status or record.verification_status,
            "is_blog": record.is_blog,
            "blog_score": record.blog_score,
            "blog_notes": record.blog_notes,
            "verification_quality": record.verification_quality,
            "verification_status": record.verification_status,
            "verification_notes": record.verification_notes,
            "source": record.source,
            "created_at": record.created_at,
            "upload_id": record.upload_id,
            # Multiple emails
            "email_2": record.email_2,
            "email_3": record.email_3,
            "email_2_verified": record.email_2_verified,
            "email_3_verified": record.email_3_verified,
            "email_2_quality": record.email_2_quality,
            "email_3_quality": record.email_3_quality,
            "email_2_status": record.email_2_status,
            "email_2_notes": record.email_2_notes,
            "email_3_status": record.email_3_status,
            "email_3_notes": record.email_3_notes,
            # Social links
            "linkedin": record.linkedin,
            "instagram": record.instagram,
            "facebook": record.facebook,
            "contact_form": record.contact_form,
            # Email campaign tracking
            "email_sent": record.email_sent,
            "email_sent_date": record.email_sent_date,
            # Additional metadata
            "phone": record.phone,
            "job_title": record.job_title,
            "notes": record.notes
        }
        for record in email_records
    ]

@app.get("/api/email/data/{data_id}")
async def get_email_data(
    data_id: int,
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "desc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    upload = db.query(DataUpload).filter(
        DataUpload.id == data_id,
        DataUpload.user_id == current_user.id
    ).first()

    if not upload:
        raise HTTPException(status_code=404, detail="Data upload not found")

    query = db.query(EmailData).filter(EmailData.upload_id == data_id)

    if status:
        normalized_status = status.lower()
        if normalized_status == 'verified':
            query = query.filter(
                (EmailData.verification_quality >= 85) |
                (EmailData.verified.is_(True))
            )
        elif normalized_status in {'invalid', 'failed'}:
            query = query.filter(
                (EmailData.verification_quality.isnot(None) & (EmailData.verification_quality < 85)) |
                (EmailData.verified.is_(False))
            )
        elif normalized_status == 'unverified':
            query = query.filter(EmailData.verification_quality.is_(None))

    if search:
        like_pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(EmailData.email).like(like_pattern),
                func.lower(EmailData.company).like(like_pattern),
                func.lower(EmailData.website).like(like_pattern),
                func.lower(EmailData.status).like(like_pattern),
                func.lower(EmailData.verification_status).like(like_pattern)
            )
        )

    sortable_columns: Dict[str, Any] = {
        'email': EmailData.email,
        'company': EmailData.company,
        'website': EmailData.website,
        'created_at': EmailData.created_at,
        'quality': EmailData.verification_quality
    }

    column = sortable_columns.get(sort_by or '')
    if column is not None:
        if (sort_order or '').lower() == 'asc':
            query = query.order_by(column.asc())
        else:
            query = query.order_by(column.desc())
    else:
        query = query.order_by(EmailData.created_at.desc())

    email_records = query.all()
    if not email_records:
        return []

    return [
        {
            "row_id": record.id,
            "id": record.id,
            "email": record.email,
            "name": record.name,
            "company": record.company,
            "website": record.website,
            "verified": bool(record.verification_quality and record.verification_quality >= 85) or bool(record.verified),
            "status": record.status or record.verification_status,
            "is_blog": record.is_blog,
            "blog_score": record.blog_score,
            "blog_notes": record.blog_notes,
            "verification_quality": record.verification_quality,
            "verification_status": record.verification_status,
            "verification_notes": record.verification_notes,
            "source": record.source,
            "created_at": record.created_at,
            "upload_id": record.upload_id,
            # Multiple emails
            "email_2": record.email_2,
            "email_3": record.email_3,
            "email_2_verified": record.email_2_verified,
            "email_3_verified": record.email_3_verified,
            "email_2_quality": record.email_2_quality,
            "email_3_quality": record.email_3_quality,
            "email_2_status": record.email_2_status,
            "email_2_notes": record.email_2_notes,
            "email_3_status": record.email_3_status,
            "email_3_notes": record.email_3_notes,
            # Social links
            "linkedin": record.linkedin,
            "instagram": record.instagram,
            "facebook": record.facebook,
            "contact_form": record.contact_form,
            # Email campaign tracking
            "email_sent": record.email_sent,
            "email_sent_date": record.email_sent_date,
            # Additional metadata
            "phone": record.phone,
            "job_title": record.job_title,
            "notes": record.notes
        }
        for record in email_records
    ]

@app.get("/api/email/download-excel/{data_id}")
async def download_excel(
    data_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    upload = db.query(DataUpload).filter(
        DataUpload.id == data_id,
        DataUpload.user_id == current_user.id
    ).first()

    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    email_records = (
        db.query(EmailData)
        .filter(EmailData.upload_id == upload.id)
        .order_by(EmailData.created_at.asc())
        .all()
    )

    if not email_records:
        raise HTTPException(status_code=404, detail="No email data found")

    rows = []
    for record in email_records:
        quality = record.verification_quality
        verified_flag = (quality is not None and quality >= 85) or bool(record.verified)
        rows.append({
            "Company": record.company,
            "Website": record.website,
            "Email 1": record.email,
            "Email 1 Score": quality,
            "Email 1 Status": record.verification_status or record.status,
            "Email 1 Reason": record.verification_notes,
            "Email 2": record.email_2,
            "Email 2 Score": record.email_2_quality,
            "Email 2 Status": record.email_2_status,
            "Email 2 Reason": record.email_2_notes,
            "Email 3": record.email_3,
            "Email 3 Score": record.email_3_quality,
            "Email 3 Status": record.email_3_status,
            "Email 3 Reason": record.email_3_notes,
            "Name": record.name,
            "Phone": record.phone,
            "Job Title": record.job_title,
            "LinkedIn": record.linkedin,
            "Instagram": record.instagram,
            "Facebook": record.facebook,
            "Contact Form": record.contact_form,
            "Is Blog": record.is_blog,
            "Blog Score": record.blog_score,
            "Blog Notes": record.blog_notes,
            "Email Sent": record.email_sent,
            "Email Sent Date": record.email_sent_date.isoformat() if record.email_sent_date else None,
            "Notes": record.notes,
            "Source": record.source,
            "Created At": record.created_at.isoformat() if record.created_at else None,
            "Upload ID": record.upload_id,
            "Original Upload File": upload.filename,
        })

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Processed Emails')

    output.seek(0)

    original_stem = Path(upload.filename).stem if upload.filename else f"upload_{data_id}"
    safe_stem = sanitize_filename(original_stem, f"upload_{data_id}")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    final_name = f"{safe_stem}_processed_{timestamp}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={final_name}"}
    )

@app.get("/api/email/history")
async def get_data_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    uploads = db.query(DataUpload).filter(DataUpload.user_id == current_user.id).order_by(DataUpload.created_at.desc()).all()
    
    result = []
    for upload in uploads:
        # Count verified/invalid emails
        email_records = db.query(EmailData).filter(EmailData.upload_id == upload.id).all()
        verified_count = sum(1 for record in email_records if (record.verification_quality or 0) >= 85 or record.verified)
        invalid_count = sum(1 for record in email_records if record.verification_quality is not None and record.verification_quality < 85)
        pending_count = len(email_records) - verified_count - invalid_count
        unique_emails = {record.email for record in email_records if record.email}
        unique_websites = {record.website for record in email_records if record.website}
        
        result.append({
            "id": upload.id,
            "filename": upload.filename,
            "created_at": upload.created_at,
            "total_emails": len(email_records),
            "verified_count": verified_count,
            "invalid_count": invalid_count,
            "pending_count": pending_count,
            "unique_emails": len(unique_emails),
            "unique_websites": len(unique_websites)
        })
    
    return result


@app.delete("/api/email/uploads/{upload_id}")
async def delete_upload(
    upload_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    upload = db.query(DataUpload).filter(
        DataUpload.id == upload_id,
        DataUpload.user_id == current_user.id
    ).first()

    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    db.query(EmailData).filter(EmailData.upload_id == upload_id).delete()
    db.delete(upload)
    db.commit()

    return {"message": "Upload deleted successfully", "upload_id": upload_id}


# CRUD Endpoints for CRM-style data management
@app.put("/api/email/update/{email_id}")
async def update_email_record(
    email_id: int,
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a single email record"""
    # Get the record
    record = db.query(EmailData).filter(EmailData.id == email_id).first()

    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Verify user owns this record (via upload)
    upload = db.query(DataUpload).filter(DataUpload.id == record.upload_id).first()
    if not upload or (upload.user_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=403, detail="Access denied")

    # Update fields with proper type conversion
    from datetime import datetime
    
    updatable_fields = [
        'email', 'name', 'company', 'website', 'verified', 'status',
        'is_blog', 'blog_score', 'blog_notes',
        'verification_quality', 'verification_status', 'verification_notes',
        'email_2', 'email_3', 'email_2_verified', 'email_3_verified',
        'email_2_quality', 'email_3_quality',
        'linkedin', 'instagram', 'facebook', 'contact_form',
        'email_sent', 'email_sent_date',
        'phone', 'job_title', 'notes'
    ]

    for field in updatable_fields:
        if field in data:
            value = data[field]
            # Convert ISO datetime strings to Python datetime objects
            if field.endswith('_date') and isinstance(value, str):
                try:
                    # Handle different ISO formats
                    if 'T' in value:
                        # ISO format with time
                        if value.endswith('Z'):
                            # Replace Z with +00:00 for UTC
                            value = value[:-1] + '+00:00'
                        elif not ('+' in value or '-' in value[-6:]):
                            # No timezone info, assume UTC
                            value = value + '+00:00'
                        value = datetime.fromisoformat(value)
                    else:
                        # Just date format
                        value = datetime.fromisoformat(value)
                except (ValueError, TypeError) as e:
                    print(f"Failed to parse date '{value}': {e}")
                    # If parsing fails, skip this update
                    continue
            setattr(record, field, value)

    db.commit()
    db.refresh(record)

    return {"message": "Record updated successfully", "id": email_id}


@app.delete("/api/email/delete/{email_id}")
async def delete_email_record(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a single email record"""
    record = db.query(EmailData).filter(EmailData.id == email_id).first()

    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Verify user owns this record
    upload = db.query(DataUpload).filter(DataUpload.id == record.upload_id).first()
    if not upload or (upload.user_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(record)
    db.commit()

    return {"message": "Record deleted successfully"}


@app.post("/api/email/bulk-update")
async def bulk_update_email_records(
    update_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk update email records (e.g., mark as sent)"""
    from datetime import datetime
    
    email_ids = update_data.get('ids', [])
    updates = update_data.get('updates', {})
    
    # Debug: Print the incoming data
    print(f"DEBUG: email_ids = {email_ids}")
    print(f"DEBUG: updates = {updates}")

    if not email_ids:
        raise HTTPException(status_code=400, detail="No IDs provided")

    # Get records
    records = db.query(EmailData).filter(EmailData.id.in_(email_ids)).all()

    updated_count = 0
    for record in records:
        # Verify ownership
        upload = db.query(DataUpload).filter(DataUpload.id == record.upload_id).first()
        if upload and (upload.user_id == current_user.id or current_user.is_admin):
            # Apply updates with proper type conversion
            for field, value in updates.items():
                if hasattr(record, field):
                    # Convert ISO datetime strings to Python datetime objects
                    if field.endswith('_date') and isinstance(value, str):
                        try:
                            # Handle different ISO formats
                            if 'T' in value:
                                # ISO format with time
                                if value.endswith('Z'):
                                    # Replace Z with +00:00 for UTC
                                    value = value[:-1] + '+00:00'
                                elif not ('+' in value or '-' in value[-6:]):
                                    # No timezone info, assume UTC
                                    value = value + '+00:00'
                                value = datetime.fromisoformat(value)
                            else:
                                # Just date format
                                value = datetime.fromisoformat(value)
                        except (ValueError, TypeError) as e:
                            print(f"Failed to parse date '{value}': {e}")
                            # If parsing fails, skip this update
                            continue
                    setattr(record, field, value)
            updated_count += 1

    db.commit()

    return {"message": f"Updated {updated_count} records", "count": updated_count}


@app.post("/api/email/bulk-delete")
async def bulk_delete_email_records(
    delete_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk delete email records"""
    email_ids = delete_data.get('ids', [])

    if not email_ids:
        raise HTTPException(status_code=400, detail="No IDs provided")

    # Get records
    records = db.query(EmailData).filter(EmailData.id.in_(email_ids)).all()

    deleted_count = 0
    for record in records:
        # Verify ownership
        upload = db.query(DataUpload).filter(DataUpload.id == record.upload_id).first()
        if upload and (upload.user_id == current_user.id or current_user.is_admin):
            db.delete(record)
            deleted_count += 1

    db.commit()

    return {"message": f"Deleted {deleted_count} records", "count": deleted_count}


def build_dashboard_summary(current_user: User, db: Session) -> Dict[str, Any]:
    uploads = db.query(DataUpload).filter(DataUpload.user_id == current_user.id).order_by(DataUpload.created_at.desc()).all()
    upload_map = {upload.id: upload for upload in uploads}

    def normalize_website(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        if '://' not in raw:
            raw = f'https://{raw}'
        try:
            parsed = urlparse(raw)
            host = parsed.netloc or parsed.path
            if not host:
                return None
            return host.lower().lstrip('www.')
        except Exception:
            return raw.lower()

    email_query = db.query(EmailData).join(DataUpload, EmailData.upload_id == DataUpload.id).filter(DataUpload.user_id == current_user.id)
    email_records = email_query.all()

    unique_entries: Dict[str, Dict[str, Any]] = {}
    unique_emails: Dict[str, Dict[str, Any]] = {}

    for record in email_records:
        normalized_email = (record.email or '').strip().lower()
        website = normalize_website(record.website)
        verified_flag = bool(record.verification_quality and record.verification_quality >= 85) or bool(record.verified)
        status_reason = record.verification_status or record.status

        if website:
            entry = unique_entries.setdefault(website, {
                'website': website,
                'upload_ids': set(),
                'email_count': 0,
                'last_upload': None
            })
            entry['email_count'] += 1
            entry['upload_ids'].add(record.upload_id)
            upload = upload_map.get(record.upload_id)
            if upload:
                entry['last_upload'] = max(entry['last_upload'], upload.created_at) if entry['last_upload'] else upload.created_at

        if normalized_email:
            existing = unique_emails.get(normalized_email)
            current_info = {
                'email': normalized_email,
                'website': website,
                'company': record.company,
                'verified': verified_flag,
                'quality': record.verification_quality,
                'status': status_reason,
                'notes': record.verification_notes,
                'source': record.source,
                'upload_ids': {record.upload_id},
                'last_seen': record.created_at
            }

            if existing:
                existing['upload_ids'].add(record.upload_id)
                if current_info['last_seen'] and (existing['last_seen'] is None or current_info['last_seen'] > existing['last_seen']):
                    existing['last_seen'] = current_info['last_seen']
                existing_quality = existing.get('quality') or 0
                new_quality = current_info.get('quality') or 0
                if new_quality >= existing_quality:
                    existing.update({
                        'website': current_info['website'],
                        'company': current_info['company'],
                        'verified': current_info['verified'],
                        'quality': current_info['quality'],
                        'status': current_info['status'],
                        'notes': current_info['notes'],
                        'source': current_info['source']
                    })
            else:
                unique_emails[normalized_email] = current_info

    for upload in uploads:
        try:
            stored_records = json.loads(upload.data_json or '[]')
        except (json.JSONDecodeError, TypeError):
            stored_records = []

        if isinstance(stored_records, dict):
            stored_records = [stored_records]

        for item in stored_records:
            if not isinstance(item, dict):
                continue
            candidate = item.get('website') or item.get('domain') or item.get('url')
            website = normalize_website(candidate)
            if not website:
                continue
            entry = unique_entries.setdefault(website, {
                'website': website,
                'upload_ids': set(),
                'email_count': 0,
                'last_upload': None
            })
            entry['upload_ids'].add(upload.id)
            entry['last_upload'] = max(entry['last_upload'], upload.created_at) if entry['last_upload'] else upload.created_at

    entries_list = []
    for website, info in unique_entries.items():
        entries_list.append({
            'website': website,
            'upload_ids': sorted(info['upload_ids']),
            'email_count': info.get('email_count', 0),
            'last_upload': info['last_upload'].isoformat() if info['last_upload'] else None
        })

    entries_list.sort(
        key=lambda item: item['last_upload'] or '',
        reverse=True
    )

    email_list = []
    verified_list = []
    invalid_list = []

    for email, info in unique_emails.items():
        payload = {
            'email': email,
            'website': info.get('website'),
            'company': info.get('company'),
            'verified': info.get('verified'),
            'quality': info.get('quality'),
            'status': info.get('status'),
            'notes': info.get('notes'),
            'source': info.get('source'),
            'upload_ids': sorted(info.get('upload_ids', [])),
            'last_seen': info.get('last_seen').isoformat() if info.get('last_seen') else None
        }
        email_list.append(payload)
        if payload['verified']:
            verified_list.append(payload)
        elif payload['quality'] is not None:
            invalid_list.append(payload)

    email_list.sort(
        key=lambda item: (
            1 if item.get('quality') is not None else 0,
            item.get('quality') or 0
        ),
        reverse=True
    )

    verified_list.sort(
        key=lambda item: item.get('quality') or 0,
        reverse=True
    )

    invalid_list.sort(
        key=lambda item: item.get('quality') or 0
    )

    total_entries = len(entries_list)
    total_emails = len(email_records)  # Total email records, not unique
    verified_count = sum(1 for r in email_records if (r.verification_quality and r.verification_quality >= 85) or bool(r.verified))
    invalid_count = sum(1 for r in email_records if r.verification_quality is not None and r.verification_quality < 85)
    pending_count = total_emails - verified_count - invalid_count
    total_unique_emails = len(email_list)

    return {
        'total_uploads': len(uploads),
        'total_entries': total_entries,
        'total_emails': total_unique_emails,
        'verified_emails': verified_count,
        'invalid_emails': invalid_count,
        'pending_emails': max(pending_count, 0),
        'entries': entries_list,
        'emails': email_list,
        'verified_list': verified_list,
        'invalid_list': invalid_list
    }


@app.get("/api/dashboard/summary")
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get dashboard summary - admins see all users' data, regular users see only their own"""
    return build_dashboard_summary(current_user, db)


@app.get("/api/admin/all-data")
async def get_all_users_data(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Admin endpoint to get all users' data with user information"""
    all_uploads = db.query(DataUpload).order_by(DataUpload.created_at.desc()).all()

    result = []
    for upload in all_uploads:
        user = db.query(User).filter(User.id == upload.user_id).first()
        email_records = db.query(EmailData).filter(EmailData.upload_id == upload.id).all()
        verified_count = sum(1 for record in email_records if (record.verification_quality or 0) >= 85 or record.verified)
        invalid_count = sum(1 for record in email_records if record.verification_quality is not None and record.verification_quality < 85)
        pending_count = len(email_records) - verified_count - invalid_count

        result.append({
            "id": upload.id,
            "filename": upload.filename,
            "created_at": upload.created_at,
            "user_id": upload.user_id,
            "username": user.username if user else "Unknown",
            "user_email": user.email if user else "Unknown",
            "total_emails": len(email_records),
            "verified_count": verified_count,
            "invalid_count": invalid_count,
            "pending_count": pending_count,
        })

    return result


@app.get("/api/dashboard/download")
async def download_dashboard_data(
    category: str = Query("emails"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    summary = build_dashboard_summary(current_user, db)
    category_key = (category or "").strip().lower()

    category_map = {
        'entries': ('entries', 'Entries'),
        'emails': ('emails', 'Emails'),
        'verified': ('verified_list', 'Verified Emails'),
        'invalid': ('invalid_list', 'Needs Attention'),
    }

    if category_key not in category_map:
        raise HTTPException(status_code=400, detail="Invalid download category")

    data_key, sheet_label = category_map[category_key]
    dataset = summary.get(data_key, []) or []

    if not dataset:
        raise HTTPException(status_code=404, detail="No data available for download")

    if category_key == 'entries':
        rows = [
            {
                "Website": item.get('website'),
                "Email Count": item.get('email_count', 0),
                "Upload IDs": ', '.join(str(upload_id) for upload_id in item.get('upload_ids', [])),
                "Last Upload": item.get('last_upload'),
            }
            for item in dataset
        ]
    else:
        rows = [
            {
                "Email": item.get('email'),
                "Website": item.get('website'),
                "Company": item.get('company'),
                "Verified": item.get('verified'),
                "Quality": item.get('quality'),
                "Status": item.get('status'),
                "Notes": item.get('notes'),
                "Source": item.get('source'),
                "Upload IDs": ', '.join(str(upload_id) for upload_id in item.get('upload_ids', [])),
                "Last Seen": item.get('last_seen'),
            }
            for item in dataset
        ]

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_label)

    output.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = sanitize_filename(f"dashboard_{category_key}", f"dashboard_{category_key}")
    filename = f"{safe_name}_{timestamp}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# WebSocket endpoint for real-time progress
@app.websocket("/ws/{process_id}")
async def websocket_endpoint(websocket: WebSocket, process_id: str):
    await websocket.accept()
    await pipeline_manager.add_websocket(process_id, websocket)
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        await pipeline_manager.remove_websocket(process_id)

# Pipeline endpoints
@app.post("/api/pipeline/start")
async def start_pipeline(
    pipeline_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start processing pipeline
    Expected data:
    {
        "data_id": int,  # Upload ID for existing data
        "steps": ["blog_check", "email_scrape", "email_verify"],  # Pipeline steps
        "urls": [...],  # Or direct URLs if no data_id
        "emails": [...]  # Or direct emails if no data_id
        "filter_emails": [...],  # Optional: Only process these specific emails
        "filter_websites": [...]  # Optional: Only process these specific websites
    }
    """
    data_id = pipeline_data.get('data_id')
    steps = pipeline_data.get('steps', [])
    if steps == ["blog_check", "email_scrape", "email_verify"]:
        steps = ["blog_check", "email_scrape"]
    elif steps == ["email_scrape", "email_verify"]:
        steps = ["email_scrape"]
    urls = pipeline_data.get('urls', [])
    emails = pipeline_data.get('emails', [])
    filter_emails = pipeline_data.get('filter_emails', [])
    filter_websites = pipeline_data.get('filter_websites', [])
    
    if not steps:
        raise HTTPException(status_code=400, detail="No pipeline steps specified")
    
    # Generate unique process ID
    process_id = str(uuid.uuid4())
    
    # Get data source
    data_to_process = []
    
    if data_id:
        # Load from existing upload - GET FROM DATABASE, NOT JSON!
        upload = db.query(DataUpload).filter(
            DataUpload.id == data_id,
            DataUpload.user_id == current_user.id
        ).first()
        
        if not upload:
            raise HTTPException(status_code=404, detail="Data upload not found")
        
        # CRITICAL FIX: Load from database records, not from upload.data_json
        # This ensures we update existing records instead of creating duplicates
        query = db.query(EmailData).filter(EmailData.upload_id == data_id)
        
        # Apply filters if provided
        if filter_emails:
            query = query.filter(EmailData.email.in_(filter_emails))
        if filter_websites:
            # Normalize filter websites for comparison
            normalized_filters = [w.lower().strip() for w in filter_websites if w]
            query = query.filter(
                or_(
                    EmailData.website.in_(filter_websites),
                    func.lower(EmailData.website).in_(normalized_filters)
                )
            )
        
        db_records = query.all()
        
        if not db_records:
            raise HTTPException(status_code=404, detail="No data found for this upload")
        
        # Convert database records to dict format for pipeline
        data_to_process = []
        for record in db_records:
            item = {
                'website': record.website,
                'url': record.website,
                'domain': record.website,
                'email': record.email,
                'company': record.company,
                'name': record.name,
                'is_blog': record.is_blog,
                'blog_score': record.blog_score,
            }
            data_to_process.append(item)
            
    elif urls:
        # Use provided URLs
        data_to_process = [{'url': url} for url in urls]
        
    elif emails:
        # Use provided emails
        data_to_process = [{'email': email} for email in emails]
        
    else:
        raise HTTPException(status_code=400, detail="No data source provided")
    
    # Start pipeline asynchronously
    asyncio.create_task(
        pipeline_manager.start_pipeline(
            process_id,
            data_to_process,
            steps,
            current_user.id,
            upload_id=data_id
        )
    )
    
    return {
        "process_id": process_id,
        "message": "Pipeline started",
        "steps": steps,
        "total_items": len(data_to_process)
    }

@app.get("/api/pipeline/status/{process_id}")
async def get_pipeline_status(
    process_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get status of a running pipeline"""
    status = pipeline_manager.get_process_status(process_id)
    
    if status['status'] == 'not_found':
        raise HTTPException(status_code=404, detail="Process not found")
        
    return status

@app.get("/api/pipeline/processes")
async def get_user_processes(
    current_user: User = Depends(get_current_user)
):
    """Get all processes for current user"""
    processes = pipeline_manager.get_all_processes(current_user.id)
    return processes

@app.post("/api/pipeline/stop/{process_id}")
async def stop_pipeline(
    process_id: str,
    current_user: User = Depends(get_current_user)
):
    """Stop a running pipeline"""
    if process_id in pipeline_manager.active_processes:
        process_info = pipeline_manager.active_processes[process_id]
        process_info['status'] = 'stopped'
        process_info['end_time'] = datetime.now()
        
        await pipeline_manager.send_progress(process_id, {
            'type': 'stopped',
            'message': 'Pipeline stopped by user',
            'timestamp': datetime.now().isoformat()
        })
        
        return {
            "message": "Pipeline stopped",
            "process_id": process_id,
            "processing_time": (process_info.get('end_time', datetime.now()) - process_info.get('start_time', datetime.now())).total_seconds()
        }
    else:
        raise HTTPException(status_code=404, detail="Process not found")

@app.post("/api/pipeline/force-stop/{process_id}")
async def force_stop_pipeline(
    process_id: str,
    current_user: User = Depends(get_current_user)
):
    """Force stop a hung pipeline and clean up resources"""
    if process_id in pipeline_manager.active_processes:
        process_info = pipeline_manager.active_processes[process_id]
        process_info['status'] = 'force_stopped'
        process_info['end_time'] = datetime.now()
        process_info['error'] = 'Force stopped by user due to hang/timeout'
        
        # Clean up any semaphores
        pipeline_manager._blog_pool_semaphore = None
        pipeline_manager._scrape_pool_semaphore = None
        pipeline_manager._verification_pool_semaphore = None
        
        await pipeline_manager.send_progress(process_id, {
            'type': 'force_stopped',
            'message': 'Pipeline force stopped and resources cleaned up',
            'timestamp': datetime.now().isoformat()
        })
        
        return {
            "message": "Pipeline force stopped and resources cleaned up",
            "process_id": process_id
        }
    else:
        raise HTTPException(status_code=404, detail="Process not found")

# Enhanced file upload with scraping option
@app.post("/api/upload-and-process")
async def upload_and_process(
    file: UploadFile = File(...),
    auto_scrape: bool = Form(default=False),
    auto_verify: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload file and optionally start processing pipeline"""
    allowed_extensions = ('.xlsx', '.xls', '.csv', '.tsv', '.txt')
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(allowed_extensions)} files are allowed"
        )

    try:
        # Read file based on type
        contents = await file.read()
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.lower().endswith('.tsv') or file.filename.lower().endswith('.txt'):
            df = pd.read_csv(io.BytesIO(contents), sep='\t')
        else:
            df = pd.read_excel(io.BytesIO(contents))

        # Convert to JSON for database storage
        data_json = df.to_json(orient='records')

        # Create upload record
        upload_record = DataUpload(
            filename=file.filename,
            user_id=current_user.id,
            data_json=data_json,
            processed_count=len(df)
        )
        db.add(upload_record)
        db.commit()
        db.refresh(upload_record)

        def normalize_cell(value):
            if pd.isna(value):
                return ''
            if isinstance(value, str):
                return value.strip()
            return value

        # Store individual email records
        for _, row in df.iterrows():
            row_map = {str(col).lower(): normalize_cell(row[col]) for col in df.columns}
            email_value = row_map.get('email') or row_map.get('email address') or ''
            name_value = row_map.get('name') or row_map.get('full name') or ''
            company_value = row_map.get('company') or row_map.get('organisation') or row_map.get('organization') or ''
            website_value = row_map.get('website') or row_map.get('url') or row_map.get('domain') or ''

            email_record = EmailData(
                email=email_value,
                name=name_value,
                company=company_value,
                website=website_value,
                status='Unverified',
                source='upload',
                upload_id=upload_record.id
            )
            db.add(email_record)

        db.commit()

        response = {
            "message": "File uploaded successfully",
            "upload_id": upload_record.id,
            "filename": file.filename,
            "total_records": len(df)
        }

        # Start automatic processing if requested
        if auto_scrape or auto_verify:
            steps = []
            if auto_scrape:
                steps.extend(['blog_check', 'email_scrape'])
            if auto_verify:
                steps.append('email_verify')

            if steps:
                process_id = str(uuid.uuid4())

                # Start pipeline asynchronously
                asyncio.create_task(
                    pipeline_manager.start_pipeline(
                        process_id,
                        json.loads(data_json),
                        steps,
                        current_user.id,
                        upload_id=upload_record.id
                    )
                )

                response["auto_processing"] = {
                    "process_id": process_id,
                    "steps": steps
                }

        return response

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)