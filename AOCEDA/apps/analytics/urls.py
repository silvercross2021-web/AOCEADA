from django.urls import path  # pyrefly: ignore [untyped-import]
from .views import (
    AnalyticsSummaryView, ExportCSVView, AdminStatsView, FactureDetailView,
    RechargePrepayeeView, HistoriqueJournalierView, HeatmapView, PrevisionView,
    HistoriquePDFView, RapportMensuelPDFView, HistoriqueMensuelView,
    RepartitionCapteursView,
)

urlpatterns = [
    path('summary/', AnalyticsSummaryView.as_view(), name='analytics_summary'),
    path('facture/', FactureDetailView.as_view(), name='analytics_facture'),
    path('historique/', HistoriqueJournalierView.as_view(), name='analytics_historique'),
    path('historique-mensuel/', HistoriqueMensuelView.as_view(), name='analytics_historique_mensuel'),
    path('repartition/', RepartitionCapteursView.as_view(), name='analytics_repartition'),
    path('heatmap/', HeatmapView.as_view(), name='analytics_heatmap'),
    path('prevision/', PrevisionView.as_view(), name='analytics_prevision'),
    path('recharge/', RechargePrepayeeView.as_view(), name='analytics_recharge'),
    path('export/', ExportCSVView.as_view(), name='analytics_export_csv'),
    path('export/pdf/', HistoriquePDFView.as_view(), name='analytics_export_pdf'),
    path('export/rapport-mensuel/', RapportMensuelPDFView.as_view(), name='analytics_export_rapport_mensuel'),
    path('admin/stats/', AdminStatsView.as_view(), name='analytics_admin_stats'),
]
