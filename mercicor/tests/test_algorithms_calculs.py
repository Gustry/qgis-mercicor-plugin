""" Test calcul. """

import os

from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsVectorLayer,
    QgsVectorLayerJoinInfo,
    edit,
)
from qgis.processing import run
from qgis.PyQt.QtCore import QVariant

from mercicor.processing.calcul.calcul_habitat_impact_ecologique import (
    BaseCalculHabitatImpactEtatEcologique,
)
from mercicor.processing.calcul.calcul_notes import CalculNotes
from mercicor.processing.calcul.calcul_pertes_gains import CalculPertes
from mercicor.qgis_plugin_tools import plugin_test_data_path
from mercicor.tests.base_processing import BaseTestProcessing

__copyright__ = "Copyright 2021, 3Liz"
__license__ = "GPL version 3"
__email__ = "info@3liz.org"


class TestCalculsAlgorithms(BaseTestProcessing):

    def test_expressions_mercicor(self):
        """ Test that expressions are valid. """
        gpkg = plugin_test_data_path('main_geopackage_empty_pression.gpkg', copy=True)
        layer = QgsVectorLayer('{}|layername=observations'.format(gpkg), 'test', 'ogr')

        # Fields
        for field in CalculNotes().fields:
            with self.subTest(i=field):
                self.assertGreater(layer.fields().indexOf(field), -1, field)

        # Expressions
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.layerScope(layer))

        for field, formula in CalculNotes().expressions.items():
            with self.subTest(i=field):
                self.assertGreater(layer.fields().indexOf(field), -1)

                expression = QgsExpression(formula)
                expression.prepare(context)
                self.assertFalse(expression.hasParserError())

    def test_habitat_pression_etat_ecologique(self):
        """ Test to add data in the habitat_pression_etat_ecologique layer. """
        pression_layer = QgsVectorLayer(
            plugin_test_data_path('pression.geojson'), 'pression', 'ogr')

        habitat_layer = QgsVectorLayer(plugin_test_data_path('habitat.geojson', copy=True), 'habitat', 'ogr')

        habitat_layer.startEditing()
        for field in BaseCalculHabitatImpactEtatEcologique.fields():
            if field not in habitat_layer.fields().names():
                self.assertTrue(habitat_layer.addAttribute(QgsField(field, QVariant.Double)))

        for feat in habitat_layer.getFeatures():
            for field in BaseCalculHabitatImpactEtatEcologique.fields():
                index = habitat_layer.fields().indexOf(field)
                self.assertTrue(habitat_layer.changeAttributeValue(feat.id(), index, 1))
        habitat_layer.commitChanges()

        gpkg = plugin_test_data_path('main_geopackage_empty_pression.gpkg', copy=True)
        name = 'habitat_pression_etat_ecologique'
        hab_pression_etat_ecolo_layer = QgsVectorLayer('{}|layername={}'.format(gpkg, name), name, 'ogr')

        params = {
            'HABITAT_LAYER': habitat_layer,
            'PRESSION_LAYER': pression_layer,
            'HABITAT_PRESSION_ETAT_ECOLOGIQUE_LAYER': hab_pression_etat_ecolo_layer,
        }
        os.environ['TESTING_MERCICOR'] = 'True'
        run("mercicor:calcul_habitat_pression_etat_ecologique", params)
        self.assertEqual(28, hab_pression_etat_ecolo_layer.featureCount())
        self.assertSetEqual({1, 2, 3, 4}, hab_pression_etat_ecolo_layer.uniqueValues(1))  # habitat_id
        self.assertSetEqual(
            {1, 2, 3, 4, 5, 6, 7},
            hab_pression_etat_ecolo_layer.uniqueValues(2)
        )  # pression_id
        self.assertSetEqual({1}, hab_pression_etat_ecolo_layer.uniqueValues(3))  # scenario_id

        # Get 1 pression with type 6 - Emprise
        filter_pression = QgsExpression.createFieldEqualityExpression('type_pression', 6)
        request_pression = QgsFeatureRequest(QgsExpression(filter_pression))
        request_pression.setLimit(1)
        ids = []
        for feat in pression_layer.getFeatures(filter_pression):
            ids.append(feat['id'])
        self.assertEqual(len(ids), 1)

        # Get 1 habitat_pression_etat_ecologique with type_emprise Emprise
        filter_hpee = QgsExpression.createFieldEqualityExpression('pression_id', ids[0])
        request_hpee = QgsFeatureRequest(QgsExpression(filter_hpee))
        request_hpee.setLimit(1)
        for feature in hab_pression_etat_ecolo_layer.getFeatures(request_hpee):
            self.assertIn(feature['pression_id'], ids)
            for field in BaseCalculHabitatImpactEtatEcologique.fields():
                with self.subTest(i=field):
                    self.assertEqual(0, feature[field])

        # Get 1 habitat_pression_etat_ecologique without type_emprise Emprise
        request_hpee = QgsFeatureRequest(QgsExpression('NOT ' + filter_hpee))
        request_hpee.setLimit(1)
        for feature in hab_pression_etat_ecolo_layer.getFeatures(request_hpee):
            self.assertNotIn(feature['pression_id'], ids)
            for field in BaseCalculHabitatImpactEtatEcologique.fields():
                with self.subTest(i=field):
                    self.assertNotEqual(0, feature[field])

        index = hab_pression_etat_ecolo_layer.fields().indexOf('perc_bsd')
        self.assertSetEqual({0, 1}, hab_pression_etat_ecolo_layer.uniqueValues(index))

        # Increment +10 for testing purpose
        index = habitat_layer.fields().indexOf('perc_bsd')
        with edit(habitat_layer):
            for feature in habitat_layer.getFeatures():
                habitat_layer.changeAttributeValue(feature.id(), index, feature['perc_bsd'] + 10)

        # Import it a second time, we must only update existing features with new perc_bsd
        run("mercicor:calcul_habitat_pression_etat_ecologique", params)
        self.assertEqual(28, hab_pression_etat_ecolo_layer.featureCount())
        index = hab_pression_etat_ecolo_layer.fields().indexOf('perc_bsd')
        self.assertSetEqual({0, 11}, hab_pression_etat_ecolo_layer.uniqueValues(index))
        del os.environ['TESTING_MERCICOR']

    def test_unicity_facies_name(self):
        """ Test the unicity between name and facies. """
        gpkg = plugin_test_data_path('main_geopackage_empty_pression.gpkg', copy=True)
        layer = QgsVectorLayer('{}|layername=habitat'.format(gpkg), 'test', 'ogr')
        self.assertTrue(layer.isValid())

        feature_1 = QgsFeature(layer.fields())
        feature_1.setAttribute('id', 1)
        feature_1.setAttribute('nom', 'nom 1')
        feature_1.setAttribute('facies', 'facies 1')
        feature_1.setGeometry(QgsGeometry.fromWkt('POINT(0 0)').buffer(1, 20))

        feature_2 = QgsFeature(layer.fields())
        feature_2.setAttribute('id', 2)
        feature_2.setAttribute('nom', 'nom 2')
        feature_2.setAttribute('facies', 'facies 2')
        feature_2.setGeometry(QgsGeometry.fromWkt('POINT(1 1)').buffer(1, 20))

        with edit(layer):
            layer.addFeature(feature_1)
            layer.addFeature(feature_2)

        params = {
            'INPUT': layer,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        results = run("mercicor:calcul_unicity_habitat", params)
        self.assertEqual(2, results['NUMBER_OF_UNIQUE'])
        self.assertEqual(0, results['NUMBER_OF_NON_UNIQUE'])
        self.assertEqual(0, results['OUTPUT'].featureCount())

        feature_3 = QgsFeature(layer.fields())
        feature_3.setAttribute('id', 3)
        feature_3.setAttribute('nom', 'nom 1')
        feature_3.setAttribute('facies', 'facies 1')
        feature_3.setGeometry(QgsGeometry.fromWkt('POINT(2 2)').buffer(1, 20))

        with edit(layer):
            layer.addFeature(feature_3)

        results = run("mercicor:calcul_unicity_habitat", params)
        self.assertEqual(2, results['NUMBER_OF_UNIQUE'])
        self.assertEqual(1, results['NUMBER_OF_NON_UNIQUE'])
        self.assertEqual(1, results['OUTPUT'].featureCount())
        self.assertSetEqual({1}, results['OUTPUT'].uniqueValues(0))
        self.assertSetEqual({'nom 1'}, results['OUTPUT'].uniqueValues(1))
        self.assertSetEqual({'facies 1'}, results['OUTPUT'].uniqueValues(2))

    def test_expressions_calcul_perte(self):
        """ Test that expressions are valid. """
        gpkg = plugin_test_data_path('main_geopackage_empty_pression.gpkg', copy=True)
        layer = QgsVectorLayer(
            '{}|layername=habitat_pression_etat_ecologique'.format(gpkg), 'test', 'ogr')
        scenar = QgsVectorLayer('{}|layername=scenario_pression'.format(gpkg), 'test', 'ogr')
        habitat_etat_ecolo = QgsVectorLayer(
            '{}|layername=habitat_etat_ecologique'.format(gpkg), 'test', 'ogr')

        join_habitat = QgsVectorLayerJoinInfo()
        join_habitat.setJoinFieldName('id')
        join_habitat.setJoinLayerId(habitat_etat_ecolo.id())
        join_habitat.setTargetFieldName('habitat_id')
        join_habitat.setPrefix('hab_')
        join_habitat.setJoinLayer(habitat_etat_ecolo)
        layer.addJoin(join_habitat)

        for note in CalculPertes().fields.keys():
            with self.subTest(i=note):
                self.assertGreater(scenar.fields().indexOf('perte_{}'.format(note)), -1, note)
                for field in CalculPertes().fields[note]:
                    with self.subTest(i=field):
                        self.assertGreater(layer.fields().indexOf(field), -1, field)
