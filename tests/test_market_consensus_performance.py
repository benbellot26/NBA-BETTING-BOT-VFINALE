import unittest

from nba.performance_runtime import consensus_benchmark_cohorts


class MarketConsensusPerformanceTests(unittest.TestCase):
    def test_scores_consensus_and_model_on_exact_same_games(self):
        forecasts=[{
            "game_id":"g1",
            "probabilities":{
                "home_ml":0.60,"away_ml":0.40,
                "home_spread":0.55,"away_spread":0.45,
                "over":0.52,"under":0.48,
                "spread_line":-3.5,"total_line":220.5,
            },
            "evaluation_only":{
                "consensus_entry_probability":{
                    "ML":0.58,"SPREAD":0.53,"TOTAL":0.51,
                },
                "consensus_metadata":{
                    "ML":{"book_count":4,"dispersion_pp":2.0,"pinnacle_included":False},
                    "SPREAD":{"book_count":3,"dispersion_pp":3.0,"pinnacle_included":False},
                    "TOTAL":{"book_count":5,"dispersion_pp":1.5,"pinnacle_included":False},
                },
            },
        }]
        outcomes=[{"game_id":"g1","home_score":112,"away_score":105}]
        result=consensus_benchmark_cohorts(forecasts,outcomes)
        self.assertEqual(result["ML"]["n"],1)
        self.assertEqual(result["SPREAD"]["n"],1)
        self.assertEqual(result["TOTAL"]["n"],1)
        self.assertEqual(result["ML"]["mean_book_count"],4)
        self.assertEqual(result["ML"]["median_book_count"],4.0)
        self.assertEqual(result["ML"]["minimum_book_count"],4)
        self.assertEqual(result["ML"]["maximum_book_count"],4)
        self.assertEqual(result["ML"]["median_dispersion_pp"],2.0)
        self.assertEqual(result["ML"]["p90_dispersion_pp"],2.0)
        self.assertAlmostEqual(result["ML"]["mean_model_minus_consensus_pp"],2.0)
        self.assertAlmostEqual(result["ML"]["mean_absolute_model_consensus_gap_pp"],2.0)
        self.assertEqual(result["ML"]["direction_disagreement_rate"],0.0)
        self.assertFalse(result["ML"]["used_for_certification"])
        self.assertIsNotNone(result["ML"]["consensus_brier"])
        self.assertIsNotNone(result["ML"]["model_brier_paired"])

    def test_rejects_consensus_that_claims_pinnacle_inclusion(self):
        forecasts=[{
            "game_id":"g1",
            "probabilities":{
                "home_ml":0.60,"away_ml":0.40,
                "home_spread":0.55,"away_spread":0.45,
                "over":0.52,"under":0.48,
                "spread_line":-3.5,"total_line":220.5,
            },
            "evaluation_only":{
                "consensus_entry_probability":{"ML":0.58},
                "consensus_metadata":{
                    "ML":{"book_count":3,"pinnacle_included":True},
                },
            },
        }]
        outcomes=[{"game_id":"g1","home_score":112,"away_score":105}]
        with self.assertRaisesRegex(ValueError,"includes Pinnacle"):
            consensus_benchmark_cohorts(forecasts,outcomes)


if __name__=="__main__":
    unittest.main()
