__copyright__ = "Copyright 2021, 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"

from typing import Optional, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingParameterVectorLayer,
    edit,
)

from mercicor.processing.imports.base import BaseImportAlgorithm
from mercicor.qgis_plugin_tools import load_csv, resources_path


class ImportObservationData(BaseImportAlgorithm):

    INPUT_LAYER = 'INPUT_LAYER'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def __init__(self):
        super().__init__()
        self.input_fields = None
        self.fields = None
        self.output = None

    def name(self):
        return 'import_donnees_observation'

    def displayName(self):
        return 'Import données observation'

    def shortHelpString(self):
        return (
            'Import des données des observations.\n\n'
            'L\'algortihme peut soit mettre à jour des observations existantes ou alors les rajouter dans '
            'la table destinaton.\n'
            'Pour cela, l\'algorithme s\'appuie sur le ID de la station.\n'
        )

    def initAlgorithm(self, config):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_LAYER,
                "Couche pour l'import des observations",
                [QgsProcessing.TypeVector],
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.OUTPUT_LAYER,
                "Couche des observations de destination",
                [QgsProcessing.TypeVectorPoint],
                defaultValue="observations",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        input_layer = self.parameterAsVectorLayer(parameters, self.INPUT_LAYER, context)
        self.output = self.parameterAsVectorLayer(parameters, self.OUTPUT_LAYER, context)

        self.input_fields = input_layer.fields().names()
        has_geom = 'latitude' in self.input_fields and 'longitude' in self.input_fields
        if has_geom:
            feedback.pushInfo('Les champs latitude et longitude sont détectés.')
        else:
            feedback.pushInfo('Les champs latitude et longitude ne sont pas détectés.')

        # Observation fields
        path = resources_path('data_models', 'observations.csv')
        csv = load_csv('observations', path)
        self.fields = list(csv.uniqueValues(1))
        self.fields.append('latitude')
        self.fields.append('longitude')

        for feature in input_layer.getFeatures():
            exists, existing = self.observation_exists(self.output, feature['id'])
            if exists:
                self.update_feature(feature, existing, has_geom, context, feedback)
            else:
                self.create_feature(feature, has_geom, context, feedback)

        return {}

    def update_feature(self, feature, existing, with_geom, context, feedback):
        """ Update the existing observation in the geopackage. """

        attributes = dict()
        latitude = None
        longitude = None
        for field in self.fields:
            if field == 'latitude':
                if with_geom:
                    latitude = feature['latitude']
            elif field == 'longitude':
                if with_geom:
                    longitude = feature['longitude']
            elif field in self.input_fields:
                attributes[existing.fields().indexOf(field)] = feature[field]
            else:
                feedback.pushDebugInfo('Omission du champ {}'.format(field))

        with edit(self.output):
            feedback.pushInfo('Mise à jour de l\'observation {}'.format(feature['nom_station']))
            self.output.changeAttributeValues(existing.id(), attributes)
            if latitude and longitude:
                geom = self.create_point(longitude, latitude, self.output.crs(), context)
                self.output.changeGeometry(existing.id(), geom)

    def create_feature(self, feature, with_geom, context, feedback):
        """ Create the new observation and import it in the geopackage. """
        output_feature = QgsFeature(self.output.fields())
        latitude = None
        longitude = None
        for field in self.fields:
            if field == 'latitude':
                if with_geom:
                    latitude = feature['latitude']
            elif field == 'longitude':
                if with_geom:
                    longitude = feature['longitude']
            elif field in self.input_fields:
                output_feature.setAttribute(field, feature[field])
            else:
                feedback.pushDebugInfo('Omission du champ {}'.format(field))

        if latitude and longitude:
            geom = self.create_point(longitude, latitude, self.output.crs(), context)
            output_feature.setGeometry(geom)

        with edit(self.output):
            feedback.pushInfo('Création de la nouvelle observation {}'.format(feature['nom_station']))
            self.output.addFeature(output_feature)

    @staticmethod
    def create_point(
            longitude: int, latitude: int, crs: QgsCoordinateReferenceSystem, context) -> QgsGeometry:
        """ Create the point geometry and reproject it. """
        geom = QgsGeometry.fromWkt('POINT({} {})'.format(longitude, latitude))

        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem('EPSG:4326'),
            crs,
            context.project())
        geom.transform(transform)
        return geom

    @staticmethod
    def observation_exists(layer, feature_id) -> Tuple[bool, Optional[QgsFeature]]:
        """ Check if the given observation exists. """
        request = QgsFeatureRequest()
        request.setLimit(1)
        request.setSubsetOfAttributes(['id'], layer.fields())
        request.setFilterExpression('"id" = {}'.format(feature_id))
        join_feature = QgsFeature()
        if layer.getFeatures(request).nextFeature(join_feature):
            return True, join_feature
        else:
            return False, None

    def postProcess(self, context, feedback):
        self.output_layer.reloadData()
        self.output_layer.triggerRepaint()
