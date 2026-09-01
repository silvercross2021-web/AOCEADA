from rest_framework import serializers
from .models import Prevision, RechargeCredit

class PrevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prevision
        fields = ['id', 'moisConcerné', 'annee_mois', 'consomméeEstimée_kWh', 'montantEstimé_FCFA', 'écartSurMoisPrécédent']
        read_only_fields = ['id']


class RechargeCreditSerializer(serializers.ModelSerializer):
    class Meta:
        model = RechargeCredit
        fields = ['id', 'montant_FCFA', 'dateRecharge']
        read_only_fields = fields
