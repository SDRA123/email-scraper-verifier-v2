from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    uploads = relationship("DataUpload", back_populates="user")

class DataUpload(Base):
    __tablename__ = "data_uploads"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))
    data_json = Column(Text)  # Store Excel data as JSON
    processed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="uploads")
    email_data = relationship("EmailData", back_populates="upload")

class EmailData(Base):
    __tablename__ = "email_data"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    name = Column(String, nullable=True)
    company = Column(String, nullable=True)
    website = Column(String, nullable=True)
    verified = Column(Boolean, default=False)
    status = Column(String, nullable=True)  # verification status/reason
    verification_quality = Column(Integer, nullable=True)  # Quality score (0-100)
    verification_status = Column(String, nullable=True)  # detailed verification status
    verification_notes = Column(String, nullable=True)  # verification notes/details
    is_blog = Column(Boolean, nullable=True)
    blog_score = Column(Integer, nullable=True)
    blog_notes = Column(String, nullable=True)
    source = Column(String, nullable=True)
    upload_id = Column(Integer, ForeignKey("data_uploads.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # New fields for enhanced functionality
    email_2 = Column(String, nullable=True)  # Second scraped email
    email_3 = Column(String, nullable=True)  # Third scraped email
    email_2_verified = Column(Boolean, nullable=True)
    email_3_verified = Column(Boolean, nullable=True)
    email_2_quality = Column(Integer, nullable=True)
    email_3_quality = Column(Integer, nullable=True)
    email_2_status = Column(String, nullable=True)  # Email 2 verification status
    email_2_notes = Column(String, nullable=True)  # Email 2 verification notes
    email_3_status = Column(String, nullable=True)  # Email 3 verification status
    email_3_notes = Column(String, nullable=True)  # Email 3 verification notes

    # Social and contact links
    linkedin = Column(String, nullable=True)
    instagram = Column(String, nullable=True)
    facebook = Column(String, nullable=True)
    contact_form = Column(String, nullable=True)

    # Email campaign tracking
    email_sent = Column(Boolean, default=False)
    email_sent_date = Column(DateTime, nullable=True)

    # Additional metadata
    phone = Column(String, nullable=True)
    job_title = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Relationship
    upload = relationship("DataUpload", back_populates="email_data")