__copyright__ = "Copyright 2020, 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"

import os.path

from pathlib import Path

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingParameterCrs,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterString,
    QgsVectorFileWriter,
    QgsVectorLayer,
    edit,
)

from mercicor.definitions.project_type import ProjectType
from mercicor.definitions.tables import tables
from mercicor.processing.project.base import BaseProjectAlgorithm
from mercicor.qgis_plugin_tools import load_csv, resources_path


class BaseCreateGeopackageProject(BaseProjectAlgorithm):

    FILE_GPKG = 'FILE_GPKG'
    PROJECT_CRS = 'PROJECT_CRS'
    PROJECT_NAME = 'PROJECT_NAME'
    PROJECT_EXTENT = 'PROJECT_EXTENT'
    OUTPUT_LAYERS = 'OUTPUT_LAYERS'

    @property
    def project_type(self) -> ProjectType:
        # noinspection PyTypeChecker
        return NotImplementedError

    @property
    def glossary(self) -> dict:
        # noinspection PyTypeChecker
        return NotImplementedError

    def name(self):
        return 'create_geopackage_project_{}'.format(self.project_type.label)

    def displayName(self):
        return 'Créer le projet de {} de la zone d\'étude'.format(self.project_type.label)

    def shortHelpString(self):
        return (
            "Pour commencer une nouvelle zone d'étude, vous devez d'abord créer le geopackage pour le projet "
            "de {}".format(self.project_type.label))

    def initAlgorithm(self, config):

        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.FILE_GPKG,
                'Fichier Geopackage',
                fileFilter='Projet geopackage (*.gpkg)',
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.PROJECT_NAME,
                'Nom de la zone d\'étude',
                defaultValue='',
                optional=False
            )
        )

        # target project crs
        self.addParameter(
            QgsProcessingParameterCrs(
                self.PROJECT_CRS,
                'CRS du project',
                defaultValue='EPSG:2154',
                optional=False,
            )
        )

        # target project extent
        self.addParameter(
            QgsProcessingParameterExtent(
                self.PROJECT_EXTENT,
                'Emprise du projet',
                defaultValue=''
            )
        )

        self.addOutput(
            QgsProcessingOutputMultipleLayers(
                self.OUTPUT_LAYERS,
                'Couches de sorties'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        base_name = self.parameterAsString(parameters, self.FILE_GPKG, context)
        project_name = self.parameterAsString(parameters, self.PROJECT_NAME, context)
        extent = self.parameterAsExtent(parameters, self.PROJECT_EXTENT, context)
        crs = self.parameterAsCrs(parameters, self.PROJECT_CRS, context)

        feedback.pushInfo(
            'Création du projet de {type} : {name}'.format(type=self.project_type.label, name=project_name))

        parent_base_name = str(Path(base_name).parent)
        if not base_name.endswith('.gpkg'):
            base_name = os.path.join(parent_base_name, Path(base_name).stem + '.gpkg')

        if os.path.exists(base_name):
            feedback.reportError('Le fichier existe déjà. Ré-écriture du fichier…')

        self.create_geopackage(self.project_type, base_name, crs, context.project().transformContext())

        output_layers = self.load_layers(self.project_type, base_name, feedback)

        # Add metadata
        feature = QgsFeature(output_layers['metadata'].fields())
        feature.setAttribute('project_name', project_name)
        feature.setAttribute('crs', str(crs.authid()))
        feature.setAttribute('extent', extent.asWktPolygon())
        feature.setAttribute('project_type', self.project_type.label)
        with edit(output_layers['metadata']):
            output_layers['metadata'].addFeature(feature)

        # Add glossary
        for table, labels in self.glossary.items():
            with edit(output_layers[table]):
                for i, label in enumerate(labels):
                    feature = QgsFeature(output_layers[table].fields())
                    feature.setAttribute('key', i + 1)
                    feature.setAttribute('label', label)
                    output_layers[table].addFeature(feature)

        # Load layers in the project
        output_id = []
        for layer in output_layers.values():
            context.temporaryLayerStore().addMapLayer(layer)
            context.addLayerToLoadOnCompletion(
                layer.id(),
                QgsProcessingContext.LayerDetails(
                    layer.name(),
                    context.project(),
                    self.OUTPUT_LAYERS
                )
            )
            context.project().setTitle(project_name)
            output_id.append(layer.id())

        return {self.FILE_GPKG: base_name, self.OUTPUT_LAYERS: output_id}

    @staticmethod
    def load_layers(project_type: ProjectType, base_name, feedback):
        """ Create vector layer object from URI. """
        output_layers = {}
        for table in project_type.layers:
            destination = QgsVectorLayer('{}|layername={}'.format(base_name, table), table, 'ogr')
            if not destination.isValid():
                raise QgsProcessingException(
                    '* ERROR: Can\'t load layer {} in {}'.format(table, base_name))

            feedback.pushInfo('The layer {} has been created'.format(table))
            output_layers[table] = destination

        return output_layers

    @staticmethod
    def create_geopackage(project_type: ProjectType, file_path, crs, transform_context) -> None:
        """ Create the geopackage for the given path. """
        encoding = 'UTF-8'
        driver_name = QgsVectorFileWriter.driverForExtension('gpkg')
        for table in project_type.layers:

            layer_path = str(tables[table])
            if layer_path != 'None':
                layer_path += "?crs={}".format(crs.authid())

            vector_layer = QgsVectorLayer(layer_path, table, "memory")
            data_provider = vector_layer.dataProvider()

            fields = QgsFields()

            path = resources_path('data_models', '{}.csv'.format(table))
            csv = load_csv(table, path)

            for csv_feature in csv.getFeatures():
                field = QgsField(name=csv_feature['name'], type=int(csv_feature['type']))
                field.setComment(csv_feature['comment'])
                field.setAlias(csv_feature['alias'])
                fields.append(field)

            del csv

            # add fields
            data_provider.addAttributes(fields)
            vector_layer.updateFields()

            # set create file layer options
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = driver_name
            options.fileEncoding = encoding

            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
            if os.path.exists(file_path):
                options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

            options.layerName = vector_layer.name()
            options.layerOptions = ['FID=id']

            # write file
            if Qgis.QGIS_VERSION_INT >= 31900:
                write_result, error_message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                    vector_layer,
                    file_path,
                    transform_context,
                    options)
            else:
                # 3.10 <= QGIS <3.18
                write_result, error_message = QgsVectorFileWriter.writeAsVectorFormatV2(
                    vector_layer,
                    file_path,
                    transform_context,
                    options)

            # result
            if write_result != QgsVectorFileWriter.NoError:
                raise QgsProcessingException('* ERROR: {}'.format(error_message))

            del fields
            del data_provider
            del vector_layer


class CreateGeopackageProjectPression(BaseCreateGeopackageProject):

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.Pression

    @property
    def glossary(self) -> dict:
        # If you edit these labels, you MUST change in the resources/qml/style folder as well
        return {
            'liste_type_pression': ['Très faible', 'Faible', 'Moyenne', 'Forte', 'Très forte', 'Emprise'],
        }


class CreateGeopackageProjectCompensation(BaseCreateGeopackageProject):

    @property
    def project_type(self) -> ProjectType:
        return ProjectType.Compensation

    @property
    def glossary(self) -> dict:
        return {}
