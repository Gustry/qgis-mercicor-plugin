""" Test import data. """

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    edit,
)
from qgis.processing import run

from mercicor.qgis_plugin_tools import plugin_test_data_path
from mercicor.tests.base_processing import BaseTestProcessing

__copyright__ = "Copyright 2021, 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"


class TestImportAlgorithms(BaseTestProcessing):

    @classmethod
    def import_data(cls, projection, pression_layer):
        """ Internal function to import data. """
        layer_to_import = QgsVectorLayer(
            f'MultiPolygon?crs=epsg:{projection}&field=id:integer&field=expression:string(20)&index=yes',
            'polygon',
            'memory')

        if projection == '2154':
            x = 700000  # NOQA VNE001
            y = 7000000  # NOQA VNE001
        else:
            x = 3.0  # NOQA VNE001
            y = 50.0  # NOQA VNE001

        with edit(layer_to_import):
            feature = QgsFeature(layer_to_import.fields())
            feature.setGeometry(QgsGeometry.fromMultiPolygonXY(
                [
                    [
                        [
                            QgsPointXY(0 + x, 0 + y), QgsPointXY(5 + x, 0 + y), QgsPointXY(5 + x, 5 + y),
                            QgsPointXY(0 + x, 5 + y), QgsPointXY(0 + x, 0 + y)
                        ]
                    ],
                    [
                        [
                            QgsPointXY(5 + x, 0 + y), QgsPointXY(10 + x, 0 + y), QgsPointXY(10 + x, 5 + y),
                            QgsPointXY(5 + x, 5 + y), QgsPointXY(5 + x, 0 + y)
                        ]
                    ]
                ]
            ))
            feature.setAttributes([1, "if(area($geometry) = 25, 1,5)"])
            layer_to_import.addFeature(feature)

        assert 1 == layer_to_import.featureCount()

        count = pression_layer.featureCount()

        params = {
            "INPUT_LAYER": layer_to_import,
            "EXPRESSION_FIELD": 'expression',
            "OUTPUT_LAYER": pression_layer,
        }
        run("mercicor:import_donnees_pression", params)

        assert count + 2 == pression_layer.featureCount()
        return layer_to_import

    def test_import_pressure_data(self):
        """ Test to import pressure data. """
        project = QgsProject()
        context = QgsProcessingContext()
        context.setProject(project)

        gpkg = plugin_test_data_path('main_geopackage_empty.gpkg', copy=True)

        name = 'pression'
        pression_layer = QgsVectorLayer('{}|layername={}'.format(gpkg, name), name, 'ogr')
        self.assertTrue(pression_layer.isValid())
        project.addMapLayer(pression_layer)

        projections = ['2154', '4326']
        for i, proj in enumerate(projections):
            layer_to_import = self.import_data(proj, pression_layer)

            self.assertEqual(2 * (i + 1), pression_layer.featureCount())

            if proj == '2154':
                index = pression_layer.fields().indexOf('type_pression')
                self.assertSetEqual({1}, pression_layer.uniqueValues(index))

                self.assertEqual(layer_to_import.extent(), QgsRectangle(700000, 7000000, 700010, 7000005))
            else:
                self.assertEqual(layer_to_import.extent(), QgsRectangle(3, 50, 13, 55))

    def test_import_habitat_data(self):
        """ Test to import habitat data. """
        gpkg = plugin_test_data_path('main_geopackage_empty.gpkg', copy=True)
        target_layer = QgsVectorLayer('{}|layername={}'.format(gpkg, 'habitat'), 'habitat', 'ogr')
        self.assertEqual(0, target_layer.featureCount())

        import_layer = QgsVectorLayer(plugin_test_data_path('import_habitat.geojson'), 'habitat', 'ogr')
        self.assertTrue(import_layer.isValid())
        self.assertEqual(1, import_layer.featureCount())
        params = {
            "INPUT_LAYER": import_layer,
            "EXPRESSION_FIELD": 'expression',
            "NAME_FIELD": 'nom',
            "OUTPUT_LAYER": target_layer,
        }
        run("mercicor:import_donnees_habitat", params)
        index = target_layer.fields().indexOf('sante')

        self.assertEqual(2, target_layer.featureCount())
        self.assertSetEqual({1}, target_layer.uniqueValues(index))
        self.assertEqual(target_layer.extent(), QgsRectangle(700000, 7000000, 700010, 7000005))
