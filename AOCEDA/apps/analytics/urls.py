from django.urls import path  # pyrefly: ignore [untyped-import]
from .views import (
    AnalyticsSummaryView, ExportCSVView, AdminStatsView, FactureDetailView,
    RechargePrepayeeView, HistoriqueJournalierView, HeatmapView,
)

urlpatterns = [
    path('summary/', AnalyticsSummaryView.as_view(), name='analytics_summary'),
    path('facture/', FactureDetailView.as_view(), name='analytics_facture'),
    path('historique/', HistoriqueJournalierView.as_view(), name='analytics_historique'),
    path('heatmap/', HeatmapView.as_view(), name='analytics_heatmap'),
    path('recharge/', RechargePrepayeeView.as_view(), name='analytics_recharge'),
    path('export/', ExportCSVView.as_view(), name='analytics_export_csv'),
    path('admin/stats/', AdminStatsView.as_view(), name='analytics_admin_stats'),
]
