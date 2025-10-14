"""
Duplicate Removal Utility
Removes duplicate entries based on website and email addresses
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import EmailData
import logging

logger = logging.getLogger(__name__)

def remove_duplicate_websites(db: Session, upload_id: int = None):
    """
    Remove duplicate entries based on website.
    Keeps the oldest record and merges data from duplicates.
    """
    try:
        # Build query
        query = db.query(EmailData)
        if upload_id:
            query = query.filter(EmailData.upload_id == upload_id)

        # Find duplicates by website
        duplicates = (
            db.query(
                EmailData.website,
                func.count(EmailData.id).label('count')
            )
            .group_by(EmailData.website)
            .having(func.count(EmailData.id) > 1)
        )

        if upload_id:
            duplicates = duplicates.filter(EmailData.upload_id == upload_id)

        duplicates = duplicates.all()

        removed_count = 0
        merged_count = 0

        for dup in duplicates:
            website = dup.website
            if not website:
                continue

            # Get all records with this website
            records = (
                db.query(EmailData)
                .filter(EmailData.website == website)
            )

            if upload_id:
                records = records.filter(EmailData.upload_id == upload_id)

            records = records.order_by(EmailData.created_at.asc()).all()

            if len(records) <= 1:
                continue

            # Keep the first (oldest) record
            keep_record = records[0]
            duplicate_records = records[1:]

            # Merge data from duplicates into the keep record
            for dup_record in duplicate_records:
                # Merge email_2 and email_3
                if not keep_record.email_2 and dup_record.email:
                    if dup_record.email != keep_record.email:
                        keep_record.email_2 = dup_record.email
                        keep_record.email_2_quality = dup_record.verification_quality
                        keep_record.email_2_status = dup_record.verification_status
                        keep_record.email_2_notes = dup_record.verification_notes
                        keep_record.email_2_verified = dup_record.verified
                        merged_count += 1
                elif not keep_record.email_3 and dup_record.email:
                    if dup_record.email != keep_record.email and dup_record.email != keep_record.email_2:
                        keep_record.email_3 = dup_record.email
                        keep_record.email_3_quality = dup_record.verification_quality
                        keep_record.email_3_status = dup_record.verification_status
                        keep_record.email_3_notes = dup_record.verification_notes
                        keep_record.email_3_verified = dup_record.verified
                        merged_count += 1

                # Merge other fields if not set
                if not keep_record.company and dup_record.company:
                    keep_record.company = dup_record.company
                if not keep_record.name and dup_record.name:
                    keep_record.name = dup_record.name
                if not keep_record.phone and dup_record.phone:
                    keep_record.phone = dup_record.phone
                if not keep_record.linkedin and dup_record.linkedin:
                    keep_record.linkedin = dup_record.linkedin
                if not keep_record.instagram and dup_record.instagram:
                    keep_record.instagram = dup_record.instagram
                if not keep_record.facebook and dup_record.facebook:
                    keep_record.facebook = dup_record.facebook
                if not keep_record.contact_form and dup_record.contact_form:
                    keep_record.contact_form = dup_record.contact_form

                # Merge blog data (keep higher score)
                if dup_record.blog_score and (not keep_record.blog_score or dup_record.blog_score > keep_record.blog_score):
                    keep_record.is_blog = dup_record.is_blog
                    keep_record.blog_score = dup_record.blog_score
                    keep_record.blog_notes = dup_record.blog_notes

                # Delete the duplicate
                db.delete(dup_record)
                removed_count += 1

            db.commit()

        logger.info(f"Removed {removed_count} duplicate records, merged {merged_count} emails")
        return {"removed": removed_count, "merged": merged_count}

    except Exception as e:
        logger.error(f"Error removing duplicates: {e}")
        db.rollback()
        raise

def remove_duplicate_emails_in_record(db: Session, record_id: int):
    """
    Remove duplicate emails within a single record (email_1, email_2, email_3)
    """
    try:
        record = db.query(EmailData).filter(EmailData.id == record_id).first()
        if not record:
            return

        emails = []
        email_data = []

        # Collect unique emails with their data
        if record.email:
            emails.append(record.email.lower().strip())
            email_data.append({
                'email': record.email,
                'quality': record.verification_quality,
                'status': record.verification_status,
                'notes': record.verification_notes,
                'verified': record.verified
            })

        if record.email_2 and record.email_2.lower().strip() not in emails:
            emails.append(record.email_2.lower().strip())
            email_data.append({
                'email': record.email_2,
                'quality': record.email_2_quality,
                'status': record.email_2_status,
                'notes': record.email_2_notes,
                'verified': record.email_2_verified
            })

        if record.email_3 and record.email_3.lower().strip() not in emails:
            emails.append(record.email_3.lower().strip())
            email_data.append({
                'email': record.email_3,
                'quality': record.email_3_quality,
                'status': record.email_3_status,
                'notes': record.email_3_notes,
                'verified': record.email_3_verified
            })

        # Update record with unique emails
        if len(email_data) > 0:
            record.email = email_data[0]['email']
            record.verification_quality = email_data[0]['quality']
            record.verification_status = email_data[0]['status']
            record.verification_notes = email_data[0]['notes']
            record.verified = email_data[0]['verified']

        if len(email_data) > 1:
            record.email_2 = email_data[1]['email']
            record.email_2_quality = email_data[1]['quality']
            record.email_2_status = email_data[1]['status']
            record.email_2_notes = email_data[1]['notes']
            record.email_2_verified = email_data[1]['verified']
        else:
            record.email_2 = None
            record.email_2_quality = None
            record.email_2_status = None
            record.email_2_notes = None
            record.email_2_verified = None

        if len(email_data) > 2:
            record.email_3 = email_data[2]['email']
            record.email_3_quality = email_data[2]['quality']
            record.email_3_status = email_data[2]['status']
            record.email_3_notes = email_data[2]['notes']
            record.email_3_verified = email_data[2]['verified']
        else:
            record.email_3 = None
            record.email_3_quality = None
            record.email_3_status = None
            record.email_3_notes = None
            record.email_3_verified = None

        db.commit()

    except Exception as e:
        logger.error(f"Error removing duplicate emails in record: {e}")
        db.rollback()
        raise

def find_or_create_record_by_website(db: Session, website: str, upload_id: int):
    """
    Find existing record by website or create a new one.
    This ensures blog checker and email verifier update the same record.
    """
    if not website:
        return None

    # Normalize website
    website = website.lower().strip()
    if website.startswith('http://'):
        website = website.replace('http://', 'https://')

    # Try to find existing record
    record = (
        db.query(EmailData)
        .filter(EmailData.website == website)
        .filter(EmailData.upload_id == upload_id)
        .first()
    )

    return record
