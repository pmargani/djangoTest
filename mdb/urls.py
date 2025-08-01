from django.urls import path
from .views import ScanListView, ScanDetailView, ProcessingDetailView, set_processing_state, mark_files_deleted

urlpatterns = [
    path('scans/', ScanListView.as_view(), name='scan-list'),
    path('scans/<int:pk>/', ScanDetailView.as_view(), name='scan-detail'),
    path('processing/<int:pk>/', ProcessingDetailView.as_view(), name='processing-detail'),
    path('set-processing-state/', set_processing_state, name='set-processing-state'),
    path('mark-files-deleted/', mark_files_deleted, name='mark-files-deleted'),
]
