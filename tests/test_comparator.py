"""Adversarial synthetic checks: prevent plausible-looking false benchmark passes."""

from copy import deepcopy
import unittest

from reader_benchmark.core import InputError, compare, reference_payload_sha256


def zone(y=10,page=1):
    return {"coordinate_system":"pdf_points_top_left","crops":[{"order":1,"page":page,"x1":10,"y1":y,"x2":180,"y2":y+10}]}


def observation(label,value,y):
    return {"id":label,"source_label":label,"current_result":{"type":"numeric","source_representations":[
        {"source_value":value,"source_unit":"unit-A","comparator":None}]},
        "reference_ranges":[{"source_min":"0","source_max":"20","source_unit":"unit-A"}],
        "previous_results":[],"source_zone":zone(y),"method":None,"comment":None,
        "lab_interpretation":None,"ambiguity":None}


def fixtures():
    doc={"schema_version":"1.0","status":"success","document":{"type":"laboratory_report"},
         "parts":[{"id":"p1","type":"laboratory_report","subtype":"blood_test","sections":[
            {"id":"s1","source_title":"Synthetic section","observations":[observation("ALPHA","3",10),observation("BETA","7",40)]}]}],
         "unclassified_elements":[]}
    ref={"reference_schema_version":"1.1","reference_version":"1","case_id":"synthetic",
         "annotation_status":"complete","status":"validated","validation":{"reviewer":"synthetic-test","validated_at":"2026-01-01"},
         "source":{"sha256":"a"*64,"size_bytes":100,"page_count":2,"pages":[{"width":200,"height":200}]*2},
         "documentary_json":{k:deepcopy(v) for k,v in doc.items() if k!="status"},"annotations":{"":{"status":"verified"}},"observation_inventory":"complete"}
    approve(ref)
    run={"reader_commit":"a"*40,"schema_version":"1.0","provider":"synthetic","model":"fake",
         "parameters":{},"prompt_version":"test","prompt_sha256":"b"*64,"source":deepcopy(ref["source"]),
         "run_date":"2026-01-01T00:00:00Z","duration_ms":1,"tokens":None,"tokens_unavailable_reason":"synthetic"}
    return ref,deepcopy(doc),run


def approve(ref):
    ref["validation"]["reference_payload_sha256"]=reference_payload_sha256(ref)


def obs(doc):
    return doc["parts"][0]["sections"][0]["observations"]


class ComparatorTests(unittest.TestCase):
    def test_annotation_and_extraction_status_are_independent(self):
        r,p,m=fixtures();r["status"]="candidate";r["annotation_status"]="incomplete";p["status"]="partial"
        out=compare(r,p,m)
        self.assertEqual((out["reference_status"],out["annotation_status"],out["extraction_status"]),
                         ("candidate","incomplete","partial"))

    def test_false_complete_annotation_is_rejected(self):
        r,p,m=fixtures();r["annotations"]["/parts"]={"status":"unannotated"};approve(r)
        with self.assertRaises(InputError):compare(r,p,m)

    def test_runtime_status_is_forbidden_in_documentary_reference(self):
        r,p,m=fixtures();r["documentary_json"]["status"]="partial";approve(r)
        with self.assertRaises(InputError):compare(r,p,m)

    def test_annotation_status_change_invalidates_approval(self):
        r,p,m=fixtures();r["annotation_status"]="incomplete"
        with self.assertRaises(InputError):compare(r,p,m)

    def test_complete_annotation_does_not_mean_approved(self):
        r,p,m=fixtures();r["status"]="candidate"
        self.assertEqual(compare(r,p,m)["functional_verdict"],"CANDIDATE_REFERENCE")

    def test_range_glyph_ambiguity_does_not_hide_wrong_bound(self):
        r,p,m=fixtures()
        ref_range=obs(r["documentary_json"])[0]["reference_ranges"][0]
        ref_range["source_text"]="0–20"
        r["annotations"]["/parts/0/sections/0/observations/0/reference_ranges/0/source_text"]={"status":"ambiguous","note":"Dash glyph"}
        approve(r)
        obs(p)[0]["reference_ranges"][0]["source_max"]="200"
        out=compare(r,p,m)
        self.assertGreater(out["dimensions"]["reference_range"]["critical_error"],0)
        self.assertGreater(out["dimensions"]["reference_range"]["ambiguity"],0)

    def test_optional_nulls_do_not_create_false_differences(self):
        r,p,m=fixtures()
        obs(p)[0]["reference_ranges"][0]["source_condition"]=None
        self.assertEqual(compare(r,p,m)["functional_verdict"],"PASS")

    def test_verified_identity_can_pass(self):
        self.assertEqual(compare(*fixtures())["functional_verdict"],"PASS")

    def test_candidate_never_passes(self):
        r,p,m=fixtures();r["status"]="candidate"
        self.assertEqual(compare(r,p,m)["functional_verdict"],"CANDIDATE_REFERENCE")

    def test_partial_never_passes(self):
        r,p,m=fixtures();p["status"]="partial"
        result=compare(r,p,m)
        self.assertEqual(result["extraction_status"],"partial")
        self.assertEqual(result["functional_verdict"],"PARTIAL")

    def test_swapped_values_stay_with_source_labels(self):
        r,p,m=fixtures()
        obs(p)[0]["current_result"],obs(p)[1]["current_result"]=obs(p)[1]["current_result"],obs(p)[0]["current_result"]
        out=compare(r,p,m)
        self.assertEqual(out["observations"]["matched"],2)
        self.assertEqual(out["dimensions"]["source_value"]["critical_error"],2)

    def test_invented_unit_is_critical(self):
        r,p,m=fixtures();obs(p)[0]["current_result"]["source_representations"][0]["source_unit"]="invented"
        self.assertEqual(compare(r,p,m)["dimensions"]["unit"]["critical_error"],1)

    def test_comparator_loss_is_critical(self):
        r,p,m=fixtures();obs(r["documentary_json"])[0]["current_result"]["source_representations"][0]["comparator"]="<";approve(r)
        self.assertEqual(compare(r,p,m)["dimensions"]["comparator"]["critical_error"],1)

    def test_history_as_current_is_critical(self):
        r,p,m=fixtures();a=obs(r["documentary_json"])[0]
        a["previous_results"]=[{"source_date":"2025-01-01","source_representations":[{"source_value":"9","source_unit":"unit-A"}]}]
        approve(r);obs(p)[0]["current_result"]["source_representations"][0]["source_value"]="9"
        out=compare(r,p,m)
        self.assertGreater(out["dimensions"]["current_vs_history"]["critical_error"],0)
        self.assertGreater(out["dimensions"]["source_value"]["critical_error"],0)

    def test_reference_as_result_is_critical(self):
        r,p,m=fixtures();obs(p)[0]["current_result"]["source_representations"][0]["source_value"]="20"
        self.assertEqual(compare(r,p,m)["dimensions"]["source_value"]["critical_error"],1)

    def test_multirepresentation_pairing_not_only_multisets(self):
        r,p,m=fixtures();reps=obs(r["documentary_json"])[0]["current_result"]["source_representations"]
        reps.append({"source_value":"30","source_unit":"unit-B","comparator":None});approve(r)
        obs(p)[0]["current_result"]["source_representations"]=deepcopy(reps)
        actual=obs(p)[0]["current_result"]["source_representations"]
        actual[0]["source_unit"],actual[1]["source_unit"]=actual[1]["source_unit"],actual[0]["source_unit"]
        out=compare(r,p,m)
        self.assertEqual(out["dimensions"]["unit"].get("critical_error",0),0)
        self.assertGreater(out["dimensions"]["association"]["critical_error"],0)

    def test_missing_and_extra_are_separate(self):
        r,p,m=fixtures();obs(p).pop();obs(p).append(observation("UNRELATED","2",100))
        out=compare(r,p,m)
        self.assertEqual(out["observations"]["missing"],1)
        self.assertEqual(out["observations"]["unexpected"],1)

    def test_incomplete_inventory_cannot_call_extra_false(self):
        r,p,m=fixtures();r["observation_inventory"]="incomplete";r["annotation_status"]="incomplete";approve(r);obs(p).append(observation("GAMMA","2",100))
        out=compare(r,p,m)
        self.assertEqual(out["functional_verdict"],"INCOMPLETE")
        self.assertEqual(out["dimensions"]["extra_elements"]["unannotated"],1)

    def test_duplicate_identity_requires_arbitration(self):
        r,p,m=fixtures();obs(p).append(deepcopy(obs(p)[0]))
        out=compare(r,p,m)
        self.assertGreater(out["counts"]["ambiguity"],0)
        self.assertNotEqual(out["functional_verdict"],"PASS")

    def test_wrong_page_is_not_rescued_by_label_match(self):
        r,p,m=fixtures();obs(p)[0]["source_zone"]=zone(10,2)
        self.assertEqual(compare(r,p,m)["dimensions"]["provenance"]["critical_error"],1)

    def test_whole_page_box_cannot_replace_precise_evidence(self):
        r,p,m=fixtures();obs(p)[0]["source_zone"]["crops"][0].update(x1=0,y1=0,x2=200,y2=200)
        self.assertEqual(compare(r,p,m)["dimensions"]["provenance"]["critical_error"],1)

    def test_unannotated_child_not_masked_by_verified_parent(self):
        r,p,m=fixtures();r["annotations"]["/parts/0/sections/0/observations/0/current_result/source_representations/0/source_unit"]={"status":"unannotated"}
        r["annotation_status"]="incomplete";approve(r)
        obs(p)[0]["current_result"]["source_representations"][0]["source_unit"]="unverified"
        out=compare(r,p,m)
        self.assertEqual(out["dimensions"]["unit"]["unannotated"],1)
        self.assertNotEqual(out["functional_verdict"],"PASS")

    def test_reference_ambiguity_not_treated_as_truth(self):
        r,p,m=fixtures();r["annotations"]["/parts/0/sections/0/observations/0/reference_ranges"]={"status":"ambiguous","note":"synthetic ambiguity"}
        approve(r)
        obs(p)[0]["reference_ranges"]=[]
        self.assertEqual(compare(r,p,m)["dimensions"]["reference_range"]["ambiguity"],2)

    def test_missing_annotations_cannot_pass(self):
        r,p,m=fixtures();r["annotations"]={};r["annotation_status"]="incomplete";approve(r)
        self.assertEqual(compare(r,p,m)["functional_verdict"],"INCOMPLETE")

    def test_pdf_identity_mismatch_is_blocked(self):
        r,p,m=fixtures();m["source"]["sha256"]="c"*64
        with self.assertRaises(InputError):compare(r,p,m)

    def test_stale_reference_approval_is_blocked(self):
        r,p,m=fixtures();obs(r["documentary_json"])[0]["source_label"]="changed"
        with self.assertRaises(InputError):compare(r,p,m)

    def test_changed_annotation_cannot_keep_gold_approval(self):
        r,p,m=fixtures();r["annotations"]={}
        with self.assertRaises(InputError):compare(r,p,m)

    def test_actual_commit_must_match_manifest(self):
        r,p,m=fixtures();p["extraction_metadata"]={"module_commit":"f"*40}
        with self.assertRaises(InputError):compare(r,p,m)

    def test_unknown_prompt_identity_is_blocked(self):
        r,p,m=fixtures();m["prompt_sha256"]="v3"
        with self.assertRaises(InputError):compare(r,p,m)

    def test_reordering_ids_does_not_change_result(self):
        r,p,m=fixtures();obs(p).reverse()
        for i,x in enumerate(obs(p)):x["id"]=f"random-{i}"
        self.assertEqual(compare(r,p,m)["functional_verdict"],"PASS")

    def test_new_unclassified_content_is_visible(self):
        r,p,m=fixtures();p["unclassified_elements"]=[{"source_content":"unresolved","reason":"ambiguous"}]
        self.assertEqual(compare(r,p,m)["dimensions"]["unclassified"]["noncritical_error"],1)

    def test_changed_section_is_visible(self):
        r,p,m=fixtures();p["parts"][0]["sections"][0]["source_title"]="Changed section"
        self.assertGreater(compare(r,p,m)["dimensions"]["structure"]["noncritical_error"],0)


if __name__=="__main__":unittest.main()
