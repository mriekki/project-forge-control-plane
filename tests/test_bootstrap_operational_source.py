from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from bootstrap_operational_source import inventory, materialize_qualified, verify_proof
from bootstrap_source_binding import SourceBindingError

class OperationalSourceTests(unittest.TestCase):
    def test_exact_candidate_preserves_content_and_logical_revision_without_target_token(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            dest=root/"bootstrap"
            policy={"original":{"logicalRevision":"a"*40},"candidate":{"sourceTree":"b"*40,
                    "sourceRoot":"packages/bootstrap"}}
            def jwt(*args):
                return "test-jwt"
            def qualify(binding,descriptor,jwt,destination):
                destination.mkdir(parents=True)
                if destination.name == "candidate":
                    selected=destination/"packages/bootstrap"
                    selected.mkdir(parents=True)
                    (selected/"entry.py").write_text("print('fixture')\n")
                    (selected/"data.json").write_text('{"version":12}\n')
                    os.chmod(selected/"entry.py",0o755)
                return {"result":"verified","logicalRevision":"a"*40}
            result=materialize_qualified(policy,{},None,None,root,dest,jwt_fn=jwt,qualify_fn=qualify)
            self.assertEqual(result["logicalRevision"],"a"*40)
            self.assertFalse(result["targetWritten"])
            self.assertEqual(result["sourceFileCount"],2)
            self.assertEqual(inventory(dest)["entry.py"][0],"100755")
            proof=root/"pf-bootstrap-operational-source.json"
            proof.write_text(json.dumps(result))
            self.assertTrue(verify_proof(root,"a"*40,dest))
            (dest/"entry.py").write_text("drift")
            with self.assertRaises(SourceBindingError):
                verify_proof(root,"a"*40,dest)

    def test_wrong_qualifier_or_existing_destination_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            policy={"original":{"logicalRevision":"a"*40},"candidate":{"sourceTree":"b"*40,"sourceRoot":"packages/bootstrap"}}
            def mismatch(binding,*unused):
                return {"different":binding["sourceRoot"] if "sourceRoot" in binding else "original"}
            with self.assertRaises(SourceBindingError):
                materialize_qualified(policy,{},None,None,root,root/"bootstrap",
                    jwt_fn=lambda *a:"jwt",qualify_fn=mismatch)
            self.assertFalse((root/"bootstrap").exists())
            (root/"bootstrap").mkdir()
            with self.assertRaises(SourceBindingError):
                materialize_qualified(policy,{},None,None,root,root/"bootstrap",
                    jwt_fn=lambda *a:"jwt",qualify_fn=mismatch)

    def test_partial_copy_is_removed_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            policy={"original":{"logicalRevision":"a"*40},
                    "candidate":{"sourceTree":"b"*40,"sourceRoot":"packages/bootstrap"}}
            def qualify(binding,descriptor,jwt,path):
                path.mkdir()
                if path.name == "candidate":
                    selected=path/"packages/bootstrap"
                    selected.mkdir(parents=True)
                    (selected/"file.txt").write_text("fixture")
                return {"same":True}
            def interrupted(src,destination,**kwargs):
                destination.mkdir()
                (destination/"partial.txt").write_text("incomplete")
                raise OSError("interrupted")
            with patch("bootstrap_operational_source.shutil.copytree", side_effect=interrupted):
                with self.assertRaises(OSError):
                    materialize_qualified(policy,{},None,None,root,root/"bootstrap",
                        jwt_fn=lambda *a:"jwt",qualify_fn=qualify)
            self.assertFalse((root/"bootstrap").exists())

    def test_link_and_excess_files_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"source.txt").write_text("normal")
            (root/"link").symlink_to(root/"source.txt")
            with self.assertRaises(SourceBindingError):
                inventory(root)


    def test_adversarial_variable_remains_inert_shell_data(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"must-not-exist"
            hostile='true"; touch '+str(target)+'; echo "'
            command='if [ "$PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED" = "true" ]; then exit 99; fi'
            result=subprocess.run(["bash","--noprofile","--norc","-c",command],
                env={"PATH": os.environ.get("PATH","/usr/bin"),
                     "PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED":hostile},
                capture_output=True,check=False)
            self.assertEqual(result.returncode,0)
            self.assertFalse(target.exists())

    def test_workflow_default_off_and_target_token_after_source_revocation(self):
        workflow=Path(__file__).resolve().parents[1]/".github/workflows/generate-project.yml"
        raw=workflow.read_text()
        self.assertIn("PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED",raw)
        self.assertIn("PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED: ${{ vars.PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED }}",raw)
        self.assertIn('if [ "$PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED" = \'true\' ]; then',raw)
        self.assertNotIn('if [ "${{ vars.PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED }}" = \'true\' ]; then',raw)
        self.assertIn("BOOTSTRAP_OPERATIONAL_SOURCE_BINDING",raw)
        self.assertIn("bootstrap_operational_source.py materialize",raw)
        self.assertIn("bootstrap_operational_source.py verify",raw)
        source=raw.index("Qualify approved monorepo Bootstrap source (separate gate)")
        target=raw.index("Create target installation token")
        self.assertLess(source,target)
        self.assertIn("if: vars.PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED != 'true'",raw)
