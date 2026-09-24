import unittest

from nba.nextdata_probe import analyze_payload, extract_next_data


class NextDataProbeTests(unittest.TestCase):
    def test_extracts_next_data_json(self):
        page='<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"x":1}}}</script></html>'
        payload=extract_next_data(page)
        self.assertEqual(payload["props"]["pageProps"]["x"],1)

    def test_missing_script_is_explicit(self):
        with self.assertRaisesRegex(ValueError,"not found"):
            extract_next_data("<html></html>")

    def test_reference_candidate_needs_large_data_array_and_basketball_keys(self):
        payload={"props":{"pageProps":{"teamStats":[
            {"TEAM_NAME":f"T{i}","OFF_RATING":110+i/10,"DEF_RATING":111}
            for i in range(30)
        ]}}}
        result=analyze_payload(payload)
        self.assertTrue(result["reference_data_candidate"])
        self.assertIn("team_name",result["basketball_key_hits"])

    def test_next_config_alone_is_not_mistaken_for_stats(self):
        payload={"buildId":"abc","page":"/stats/teams/advanced",
                 "props":{"pageProps":{"locale":"en"}}}
        result=analyze_payload(payload)
        self.assertFalse(result["reference_data_candidate"])

    def test_endpoint_hints_drop_query_strings(self):
        payload={"api":"https://stats.nba.com/stats/example?apiKey=secret",
                 "relative":"/api/stats/data?token=secret"}
        result=analyze_payload(payload)
        self.assertIn("https://stats.nba.com/stats/example",result["endpoint_hints"])
        self.assertIn("/api/stats/data",result["endpoint_hints"])
        self.assertTrue(all("secret" not in x for x in result["endpoint_hints"]))


if __name__=="__main__":
    unittest.main()
