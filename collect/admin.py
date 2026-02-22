# collect/admin.py
from django.contrib import admin
from .models import ThreatAlert, CurrentInformation, NewsSource, DangerousKeyword, User, AutoNewsArticle, MapMarker, SocialMediaURL, ThreatCategory, SharedFile, Website # ✅ Correct relative import

admin.site.register(ThreatAlert)
admin.site.register(CurrentInformation)
admin.site.register(NewsSource)
admin.site.register(DangerousKeyword)
admin.site.register(User)
admin.site.register(AutoNewsArticle)
admin.site.register(MapMarker)
admin.site.register(SocialMediaURL)
admin.site.register(ThreatCategory)
admin.site.register(SharedFile)
admin.site.register(Website)

# admin.site.register(User)






