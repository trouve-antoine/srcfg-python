import unittest
import os

import srcfg as srcfg

class TestSrcfg(unittest.TestCase):
    def test_load_sample(self):
        os.environ["ENV_VAR"] = "77"

        f, errors = srcfg.parse_file("./test/sample/sub_folder/sample.srcfg")

        for e in errors:
            print(f"Error at line {e.line_nb}: {e.message}")
            print("-- line was: ", e.line)
            if e.internal_errors:
                print("-- internal errors", e.internal_errors)

        assert "global" in f
        assert "key1" in f["global"]

        assert f["global"]["key1"] == "val1 override"
        assert f["global"].get_str("key1") == "val1 override"
        
        assert f["global"]["key3"] == "42"
        assert f["global"].get_int("key3") == 42
        
        assert f["global"]["key4"] == "77"
        assert f["global"].get_int("key4") == 77
        
        assert f["global"]["key5"] == "\n".join([
            "first line",
            "that continues",
            "over lines",
            " and some spaces around  "
        ])

        assert f["global"]["key7"] == " 43dd   "
        assert f["global"]["key8"] == " yoyo ;; not a comment"

        assert "parent" in f
        assert len(f["parent"]["children"]) == 2
        assert f["parent"]["children"][0]["name"] == "first kid"
        assert f["parent"]["children"][1]["name"] == "second kid"

        assert f["another section"].get_json("key1") == [1,2,3]
        assert f["another section"].get_json("key2") == {
            "a": "a",
            "b": "c",
            "c": { "a": [1,2,3] }
        }

        assert f["global"]["key9"] == "in sample"
        assert f["global"]["key10"] == "a new value"

        assert "new section" in f
