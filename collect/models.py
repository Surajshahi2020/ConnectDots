from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
import datetime
import os
from uuid import uuid4

class User(AbstractUser):
    ROLE_CHOICES = [
        ('User', 'User'),
        ('CyberUser', 'CyberUser'),
        ('Admin', 'Admin'),
        ('SuperAdmin', 'SuperAdmin'),
        
    ]
    name = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    unit = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='User',
        help_text="User's functional role in the system"
    )
    rank = models.CharField(max_length=50, blank=True, null=True)
    social_media = models.BooleanField(
        default=False,
        help_text="Access to social media features"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Date when user was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Date when user was last updated"
    )
    is_void = models.BooleanField(
        default=False,
    )

    def __str__(self):
        return f"{self.email}--{self.username}--{self.role}-{self.unit}"
    

class ThreatCategory(models.Model):
    # 🔹 Category name - must be unique
    name = models.CharField(
        max_length=100, 
        help_text="Name of the threat category"
    )
    
    # 🔹 Who created this category
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_categories',
        help_text="User who created this category"
    )
    
    # 🔹 Is this category active?
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this category is active and visible"
    )
    
    # 🔹 Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Add unique_together constraint instead
        unique_together = ['name', 'created_by']
        verbose_name = "Threat Category"
        verbose_name_plural = "Threat Categories"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} (Created by: {self.created_by.username if self.created_by else 'System'})"
    
    @property
    def creator_name(self):
        """Get creator's username or 'System' if no creator"""
        return self.created_by.username if self.created_by else "System"
    
    @property
    def active_status(self):
        """Get human-readable active status"""
        return "Active" if self.is_active else "Inactive"
    
    def get_active_categories_for_user(user):
        """Get all active categories for a specific user"""
        if user.is_superuser:
            # Superusers see all active categories
            return ThreatCategory.objects.filter(is_active=True)
        else:
            # Regular users see categories they created OR all active categories
            # Adjust based on your requirements
            return ThreatCategory.objects.filter(
                models.Q(created_by=user) | models.Q(is_active=True)
            ).distinct()
    
class ThreatAlert(models.Model):

    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'), 
    ]

    PROVINCE_CHOICES = [
        ('koshi', 'Koshi'),
        ('madhesh', 'Madhesh'),
        ('bagmati', 'Bagmati'),
        ('gandaki', 'Gandaki'),
        ('lumbini', 'Lumbini'),
        ('karnali', 'Karnali'),
        ('sudurpaschim', 'Sudurpaschim'),
    ]

    title = models.CharField(max_length=300)
    image = models.ImageField(upload_to='threat_alerts/', blank=True, null=True)
    video = models.FileField(upload_to='threat_alerts/videos/', blank=True, null=True, 
                           help_text="Upload video files")
    province = models.CharField(
        max_length=50,
        choices=PROVINCE_CHOICES,
        blank=True,
        null=True,
        help_text="Province where activity took place"
    )
    content = models.TextField()
    category = models.ForeignKey(
        'ThreatCategory',  # Reference the ThreatCategory model
        on_delete=models.SET_NULL,  # Prevent deletion if alerts exist
        related_name='alerts',
        help_text="Select threat category",
        null=True,  # Make nullable temporarily for migration
        blank=True  # Make blankable temporarily for migration
    )
    source = models.CharField(max_length=50, default='unknown')
    url = models.URLField(unique=True)
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default='low'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_alerts',
        help_text="User who created this alert"
    )
    likes_count = models.IntegerField(default=0)
    unlikes_count = models.IntegerField(default=0)
    users_liked = models.ManyToManyField(
        User, 
        related_name='liked_alerts',
        blank=True,
        help_text="Users who liked this alert"
    )
    users_unliked = models.ManyToManyField(
        User,
        related_name='unliked_alerts', 
        blank=True,
        help_text="Users who unliked this alert"
    )

    def user_like(self, user):
        """User likes this alert"""
        if not user.is_authenticated:
            return False
            
        # Check if user already unliked - remove unlike first
        if user in self.users_unliked.all():
            self.users_unliked.remove(user)
            self.unlikes_count -= 1
            
        # Add like if not already liked
        if user not in self.users_liked.all():
            self.users_liked.add(user)
            self.likes_count += 1
            self.save()
            return True
        return False
    
    def user_unlike(self, user):
        """User unlikes this alert"""
        if not user.is_authenticated:
            return False
            
        # Check if user already liked - remove like first
        if user in self.users_liked.all():
            self.users_liked.remove(user)
            self.likes_count -= 1
            
        # Add unlike if not already unliked
        if user not in self.users_unliked.all():
            self.users_unliked.add(user)
            self.unlikes_count += 1
            self.save()
            return True
        return False

    def __str__(self):
        # Get the unit name from created_by if exists
        if self.created_by and hasattr(self.created_by, 'unit'):
            unit_info = f" - {self.created_by.unit}"
        else:
            unit_info = " - System"
        
        return f"{self.id}: {self.title[:40]}{'...' if len(self.title) > 40 else ''} ({self.created_by}, {self.created_at})"    
    
    @property
    def has_media(self):
        return bool(self.image or self.video)

    @property
    def media_type(self):
        if self.video:
            return 'video'
        elif self.image:
            return 'image'
        return 'none'
    

class CurrentInformation(models.Model):
    PROVINCE_CHOICES = [
        ('koshi', 'Koshi'),
        ('madhesh', 'Madhesh'),
        ('bagmati', 'Bagmati'),
        ('gandaki', 'Gandaki'),
        ('lumbini', 'Lumbini'),
        ('karnali', 'Karnali'),
        ('sudurpaschim', 'Sudurpaschim'),
    ]

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='created_informations',
        null=True,
        blank=True
    )

    timing = models.CharField(
        max_length=255,
        help_text="When the activity took place"
    )

    location = models.CharField(
        max_length=255,
        help_text="Where the activity took place"
    )
    leader = models.CharField(
        max_length=255,
        help_text="Name of the person in charge"
    )
    number = models.CharField(
        max_length=50,
        help_text="Contact number, ID, or team number",
        blank=True,
        null=True
    )
    vehicle = models.CharField(
        max_length=100,
        help_text="Type of vehicle used (e.g., Toyota Hilux, Motorcycle)",
        blank=True,
        null=True
    )
    description = models.TextField(
        help_text="Details of the activity or event",
        blank=True,
        null=True
    )

    province = models.CharField(
        max_length=50,
        choices=PROVINCE_CHOICES,
        blank=True,
        null=True,
        help_text="Province where activity took place"
    )

    # Optional: Add timestamp for when record was created
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    # Optional: Add status field
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        blank=True,
        null=True
    )

    class Meta:
        ordering = ['-created_at']  # Show newest first

    def __str__(self):
        return f"{self.leader} at {self.location} on {self.timing}"
    
    def __str__(self):
        # Get the unit name from created_by if exists
        if self.created_by and hasattr(self.created_by, 'unit'):
            unit_info = f" - {self.created_by.unit}"
        else:
            unit_info = " - System"
        
        return f"{self.leader} at {self.location} on {self.timing}: of {unit_info}"


class NewsSource(models.Model):
    name = models.CharField(max_length=200, help_text="Display name of the news source")
    url = models.URLField(max_length=500, help_text="Full TikTok or official URL")
    image = models.ImageField(
        upload_to='threat_alerts/source',
        blank=True,
        null=True,
        help_text="Logo or favicon (optional)"
    )

    class Meta:
        verbose_name = "News Source"
        verbose_name_plural = "News Sources"
        ordering = ['name']

    def __str__(self):
        return self.name

class DangerousKeyword(models.Model):
    """
    Dangerous keywords with free-text category field.
    """
    
    word = models.CharField(
        max_length=100, 
        db_index=True,
        help_text="The dangerous keyword or phrase"
    )
    
    category = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Category (e.g., Violence, Threats, Dehumanizing, etc.)"
    )
    
    # Provide default for existing rows
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this keyword is active"
    )

    class Meta:
        unique_together = ('word', 'category')
        verbose_name = "Dangerous Keyword"
        verbose_name_plural = "Dangerous Keywords"
        ordering = ['word']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['word']),
        ]

    def __str__(self):
        return f"{self.word} --{self.created_by}--- [{self.category}]"
    
    def save(self, *args, **kwargs):
        """Override save to normalize the word and category"""
        self.word = self.word.lower().strip()
        self.category = self.category.strip()
        super().save(*args, **kwargs)    

# In models.py
class AutoNewsArticle(models.Model):
    # Basic fields
    title = models.CharField(max_length=500)
    summary = models.TextField()
    url = models.URLField(max_length=1000)  # REMOVE unique=True
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    source = models.CharField(max_length=100)
    date = models.CharField(max_length=20)
    
    # All in one table
    content_length = models.IntegerField(default=0)
    priority = models.CharField(max_length=10, default='medium')
    threat_level = models.CharField(max_length=10, default='low')
    keywords = models.TextField(blank=True)
    categories = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_news_articles'
    )
    
    class Meta:
        ordering = ['-created_at']
        # Add this to prevent same user having duplicate URLs
        unique_together = ['url', 'created_by']
    
    def __str__(self):
        return f"{self.source}: {self.title[:100]}: {self.created_by}"

class MapMarker(models.Model):
    # Category choices (from your form)
    CATEGORY_CHOICES = [
        ('military_deployment', '🚨 Military Deployment'),
        ('protest', '✊ Protest/Rally'),
        ('violence_clash', '⚔️ Violence/Clash'),
        ('political_rally', '🏛️ Political Rally'),
        ('speech_event', '🎤 Political Speech'),
        ('other', '📌 Other Incident'),
    ]
    
    # Color choices (from your form)
    COLOR_CHOICES = [
        ('#FF0000', 'Red'),
        ('#0000FF', 'Blue'),
        ('#008000', 'Green'),
        ('#FFA500', 'Orange'),
        ('#800080', 'Purple'),
        ('#FFFF00', 'Yellow'),
    ]
    
    # Title (required) - from your form "Title *"
    title = models.CharField(max_length=255)
    
    # Description (optional) - from your form "Description"
    description = models.TextField(blank=True)
    
    # Category - from your form "Category" dropdown
    category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES, 
        default='general'
    )
    
    # Color - from your form "Marker Color" dropdown
    color = models.CharField(
        max_length=20, 
        choices=COLOR_CHOICES, 
        default='#FF0000'
    )
    
    # Location coordinates - from your form "Location: 27.0467, 85.1770"
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    # Additional info
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.latitude}, {self.longitude},  {self.category})"
    
    def get_location_string(self):
        """Get location as formatted string"""
        return f"{self.latitude:.4f}, {self.longitude:.4f}, {self.title}, {self.category}"


def upload_to(instance, filename):
    """Generate unique filename for uploaded images"""
    # Get file extension
    ext = filename.split('.')[-1].lower()
    # Generate unique filename
    unique_filename = f"{uuid4().hex}.{ext}"
    return os.path.join('social_media/photos', unique_filename)

class SocialMediaURL(models.Model):
    """Model to track URLs first, then update with found information"""
    
    # Stage 1: When URL is submitted (initial entry)
    url = models.URLField(max_length=500, unique=True)
    source_department = models.CharField(max_length=100)
    submitted_date = models.DateTimeField(auto_now_add=True)
    
    # Stage 2: Search status (updated during search)
    STATUS_CHOICES = [
        ('pending', 'Pending Search'),
        ('searching', 'Searching'),
        ('found', 'Information Found'),
        ('not_found', 'No Information Found'),
        ('error', 'Search Error'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    search_date = models.DateTimeField(null=True, blank=True)
    
    # Stage 3: When information is found (filled later)
    personnel_no = models.CharField(max_length=50, blank=True)
    rank = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=200, blank=True)
    unit = models.CharField(max_length=200, blank=True)
    user_id = models.CharField(max_length=200, blank=True)  # TikTok ID
    description = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    
    # Photo field - only file upload
    photo = models.ImageField(
        upload_to='social_media/', 
        blank=True, 
        null=True,
        verbose_name="Uploaded Photo"
    )

    photo_one = models.ImageField(
        upload_to='social_media/', 
        blank=True, 
        null=True,
        verbose_name="Uploaded Photo 1"
    )

    photo_two = models.ImageField(
        upload_to='social_media/', 
        blank=True, 
        null=True,
        verbose_name="Uploaded Photo 2"
    )


    
    # Stage 4: Completion
    completed_date = models.DateTimeField(null=True, blank=True)
    response_sent = models.BooleanField(default=False)
    
    # Add platform field if not already there
    platform = models.CharField(max_length=50, blank=True, verbose_name="Social Media Platform")
    
    class Meta:
        ordering = ['-submitted_date']
        verbose_name = "Social Media URL Tracking"
    
    def __str__(self):
        return f"{self.url[:40]}... - {self.status}"
    
    def get_photo_display(self):
        """Return the photo to display"""
        if self.photo:
            return self.photo.url
        if self.photo_one:
            return self.photo.url
        if self.photo_two:
            return self.photo.url
        return None

class SharedFile(models.Model):
    # File information
    name = models.CharField(max_length=255, verbose_name="Filename")
    file = models.FileField(upload_to='shared_files/%Y/%m/%d/', verbose_name="File")
    description = models.TextField(blank=True, verbose_name="Description")
    
    # File metadata
    size = models.PositiveIntegerField(default=0, verbose_name="Size (bytes)")
    extension = models.CharField(max_length=10, blank=True, verbose_name="File Extension")
    
    # User information
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, 
                                    related_name='uploaded_files', verbose_name="Uploaded By")
    
    # Sharing information
    shared_with = models.ManyToManyField(User, related_name='shared_files', 
                                         blank=True, verbose_name="Shared With")
    is_public = models.BooleanField(default=False, verbose_name="Public File")
    
    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Uploaded At")
    modified_at = models.DateTimeField(auto_now=True, verbose_name="Modified At")
    
    # Download tracking
    download_count = models.PositiveIntegerField(default=0, verbose_name="Download Count")
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "Shared File"
        verbose_name_plural = "Shared Files"
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Auto-calculate file size and extension before saving
        if self.file:
            self.size = self.file.size
            self.extension = os.path.splitext(self.file.name)[1].lower().replace('.', '')
        
        # Set name from filename if not provided
        if not self.name and self.file:
            self.name = os.path.basename(self.file.name)
        
        super().save(*args, **kwargs)
    
    def get_file_size_display(self):
        """Return human readable file size."""
        if self.size < 1024:
            return f"{self.size} bytes"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        elif self.size < 1024 * 1024 * 1024:
            return f"{self.size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.size / (1024 * 1024 * 1024):.1f} GB"
    
    def increment_download_count(self):
        """Increment download count."""
        self.download_count += 1
        self.save(update_fields=['download_count'])
    
    def get_icon_class(self):
        """Return appropriate FontAwesome icon class."""
        icon_map = {
            'pdf': 'fa-file-pdf',
            'doc': 'fa-file-word',
            'docx': 'fa-file-word',
            'jpg': 'fa-file-image',
            'jpeg': 'fa-file-image',
            'png': 'fa-file-image',
            'gif': 'fa-file-image',
            'zip': 'fa-file-archive',
            'rar': 'fa-file-archive',
            '7z': 'fa-file-archive',
            'txt': 'fa-file-alt',
            'csv': 'fa-file-csv',
            'xls': 'fa-file-excel',
            'xlsx': 'fa-file-excel',
        }
        return icon_map.get(self.extension, 'fa-file')
    
    def get_icon_color(self):
        """Return appropriate icon color class."""
        color_map = {
            'pdf': 'text-danger',
            'doc': 'text-primary',
            'docx': 'text-primary',
            'jpg': 'text-success',
            'jpeg': 'text-success',
            'png': 'text-success',
            'zip': 'text-warning',
            'rar': 'text-warning',
            'txt': 'text-secondary',
            'csv': 'text-success',
            'xls': 'text-success',
            'xlsx': 'text-success',
        }
        return color_map.get(self.extension, 'text-muted')
    
class Website(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField()
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name