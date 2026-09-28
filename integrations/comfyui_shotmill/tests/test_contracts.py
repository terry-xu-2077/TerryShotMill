"""Standalone CPU-only acceptance: python -m unittest discover -s tests."""
import importlib.util
from pathlib import Path
import unittest


def load(name):
    path = Path(__file__).resolve().parents[1] / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contracts = load("application_contracts")
nodes = load("nodes")


class ApplicationContractsTest(unittest.TestCase):
    def test_unknown_contract_and_version_are_rejected(self):
        for name, version in (("unknown", 1), ("generic", 2), ("generic", True)):
            with self.subTest(name=name, version=version), self.assertRaises(ValueError):
                contracts.resolve_application_contract({"applicationContract": {"name": name, "version": version}}, legacy=False)

    def test_new_protocol_needs_explicit_contract(self):
        with self.assertRaises(ValueError):
            contracts.resolve_application_contract({}, legacy=False)
        self.assertEqual(contracts.resolve_application_contract({}).name, "shotmill.video")

    def test_generic_preserves_video_workflow_defaults(self):
        prompt = {"1": {"class_type": "ShotMillDurationSelector", "inputs": {"seconds": 8}}}
        generic = contracts.resolve_application_contract({"applicationContract": {"name": "generic", "version": 1}})
        generic.bind_parameters(prompt, {"durationSeconds": 2})
        self.assertEqual(prompt["1"]["inputs"]["seconds"], 8)
        contracts.resolve_application_contract({}).bind_parameters(prompt, {"durationSeconds": 2})
        self.assertEqual(prompt["1"]["inputs"]["seconds"], 2)

    def test_generic_nodes_keep_sparse_slots_and_identity(self):
        value = {"arbitrary": "payload"}
        node = nodes.NODE_CLASS_MAPPINGS["TerryFlowBridgeIn"]()
        outputs = node.bridge(**{"* 3": value})
        self.assertIs(outputs[2], value)
        self.assertIsNone(outputs[0])
        output = nodes.NODE_CLASS_MAPPINGS["TerryFlowBridgeOut"]()
        self.assertIs(output.bridge(**{"*": value})[0], value)

    def test_legacy_node_names_remain_available(self):
        for name in ("ShotMillIOBridgeIn", "ShotMillIOBridgeOut", "ShotMillDurationSelector", "ShotMillResolutionSelector"):
            self.assertIn(name, nodes.NODE_CLASS_MAPPINGS)


if __name__ == "__main__":
    unittest.main()
