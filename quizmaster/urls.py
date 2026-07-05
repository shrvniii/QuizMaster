from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from scanner import views as scanner_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('dashboard:about')), # Redirect root URL to about page
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('schools/', include('schools.urls')),
    path('participants/', include('participants.urls')),
    path('answer-keys/', include('answer_keys.urls')),
    path('scanner/', include('scanner.urls')),
    path('results/', include('results.urls')),
    path('reports/', include('reports.urls')),
    
    # API endpoints for Bulk ZIP Upload (Batch OMR Processing)
    path('api/bulk-upload', scanner_views.BulkUploadView.as_view(), name='api_bulk_upload'),
    path('api/bulk-upload/', scanner_views.BulkUploadView.as_view()),
    path('api/batch-progress/<str:batch_id>', scanner_views.BatchProgressView.as_view(), name='api_batch_progress'),
    path('api/batch-progress/<str:batch_id>/', scanner_views.BatchProgressView.as_view()),
    path('api/batch-results/<str:batch_id>', scanner_views.BatchResultsView.as_view(), name='api_batch_results'),
    path('api/batch-results/<str:batch_id>/', scanner_views.BatchResultsView.as_view()),
]

from django.views.static import serve
from django.urls import re_path

# Serve media files in all environments since local filesystem storage is utilized
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
