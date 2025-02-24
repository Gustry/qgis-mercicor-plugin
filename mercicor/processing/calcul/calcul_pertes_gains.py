__copyright__ = "Copyright 2021, 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"

from collections import OrderedDict

from qgis.core import (
    QgsExpression,
    QgsProcessing,
    QgsProcessingParameterVectorLayer,
)
from qgis.PyQt.QtCore import NULL

from mercicor.definitions.project_type import ProjectType
from mercicor.processing.calcul.base import CalculAlgorithm


class BaseCalculPertesGains(CalculAlgorithm):

    def __init__(self):
        super().__init__()
        self.fields = OrderedDict()
        self.fields['bsd'] = ['hab_note_bsd', 'note_bsd']
        self.fields['bsm'] = ['hab_note_bsm', 'note_bsm']
        self.fields['man'] = ['hab_note_man', 'note_man']
        self.fields['pmi'] = ['hab_note_pmi', 'note_pmi']
        self.fields['ben'] = ['hab_note_ben', 'note_ben']
        self.fields['mercicor'] = ['hab_score_mercicor', 'score_mercicor']

    @property
    def project_type(self) -> ProjectType:
        # noinspection PyTypeChecker
        return NotImplementedError

    def group(self):
        return 'Calcul {}'.format(self.project_type.label)

    def groupId(self):
        return 'calcul_group_{}'.format(self.project_type.label)

    def name(self):
        return 'calcul_{}'.format(self.project_type.label)

    def displayName(self):
        return (
            'Calcul des notes de {} pour le scénario de {}'.format(
                self.project_type.calcul_type, self.project_type.label))

    def checkParameterValues(self, parameters, context):
        sources = [
            self.parameterAsVectorLayer(parameters, self.SCENARIO_IMPACT, context),
            self.parameterAsVectorLayer(parameters, self.HABITAT_IMPACT_ETAT_ECOLOGIQUE, context)
        ]
        for source in sources:
            flag, msg = self.check_layer_is_geopackage(source)
            if not flag:
                return False, msg

        return super().checkParameterValues(parameters, context)

    def shortHelpString(self):
        message = (
            'Calcul des notes de {} à partir des indicateurs MERCI-Cor\n\n'
            'Liste des notes :\n\n'.format(self.project_type.calcul_type)
        )
        for field, formula in self.fields.items():
            message += (
                '{type_calcul}_{output} = '
                'La somme de ("{field_1} - {field_2} ") * surface, filtré par scénario\n\n'.format(
                    type_calcul=self.project_type.calcul_type,
                    output=field,
                    field_1=formula[0] if self.project_type == ProjectType.Pression else formula[1],
                    field_2=formula[1] if self.project_type == ProjectType.Pression else formula[0],
                )
            )
        return message

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.HABITAT_IMPACT_ETAT_ECOLOGIQUE,
                self.project_type.label_habitat_impact_etat_ecologique,
                [QgsProcessing.TypeVectorPolygon],
                defaultValue=self.project_type.couche_habitat_impact_etat_ecologique,
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.SCENARIO_IMPACT,
                self.project_type.label_scenario_impact,
                [QgsProcessing.TypeVectorAnyGeometry],
                defaultValue=self.project_type.couche_scenario_impact,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        hab_etat_ecolo = self.parameterAsVectorLayer(
            parameters, self.HABITAT_IMPACT_ETAT_ECOLOGIQUE, context)
        scenario_impact = self.parameterAsVectorLayer(parameters, self.SCENARIO_IMPACT, context)

        scenario_impact.startEditing()

        for feat in scenario_impact.getFeatures():
            scenario_id = feat['id']
            for note in self.fields.keys():
                # from "bsd" to "perte_bsd" or "gain_bsd"
                field_name = '{calcul_type}_{note}'.format(
                    calcul_type=self.project_type.calcul_type, note=note)
                feat[field_name] = 0

                filter_expression = QgsExpression.createFieldEqualityExpression('scenario_id', scenario_id)
                for feature in hab_etat_ecolo.getFeatures(filter_expression):

                    if feature[self.fields[note][1]] == NULL:
                        feedback.pushDebugInfo(
                            "Omission du calcul {} pour l'entité {}".format(field_name, feature.id()))
                        continue

                    if self.project_type == ProjectType.Pression:
                        sub_result = feature[self.fields[note][0]] - feature[self.fields[note][1]]
                    else:
                        sub_result = feature[self.fields[note][1]] - feature[self.fields[note][0]]
                    feat[field_name] += sub_result * feature.geometry().area()

            scenario_impact.updateFeature(feat)
        scenario_impact.commitChanges()

        return {}


class CalculPertes(BaseCalculPertesGains):

    HABITAT_IMPACT_ETAT_ECOLOGIQUE = 'HABITAT_PRESSION_ETAT_ECOLOGIQUE'
    SCENARIO_IMPACT = 'SCENARIO_PRESSION'

    @property
    def project_type(self):
        return ProjectType.Pression


class CalculGains(BaseCalculPertesGains):

    HABITAT_IMPACT_ETAT_ECOLOGIQUE = 'HABITAT_COMPENSATION_ETAT_ECOLOGIQUE'
    SCENARIO_IMPACT = 'SCENARIO_COMPENSATION'

    @property
    def project_type(self):
        return ProjectType.Compensation
