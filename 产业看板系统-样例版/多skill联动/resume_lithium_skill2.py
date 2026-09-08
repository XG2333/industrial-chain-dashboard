# -*- coding: utf-8 -*-
"""Resume Skill2 for lithium carbonate using the existing DeepSeek cache.

The installed financial_variable_curation CLI references threading in its
concurrent DeepSeek path without importing it. This launcher injects the
module at runtime so we do not have to edit the external package.
"""

import os
import sys
import threading

os.environ["DEEPSEEK_MAX_CONCURRENCY"] = "1"
os.environ["DEEPSEEK_BATCH_SIZE"] = "20"

import financial_variable_curation.cli as cli

cli.threading = threading

RUN_DIR = r"C:\Users\11\Documents\多skill联动\workflow_runs\20260811T084756Z_ff8cb7541bcc"
args = [
    "directory-mark",
    "--input",
    os.path.join(RUN_DIR, "01_excel_catalog_curator", "cataloged.xlsx"),
    "--rules",
    r"C:\Users\11\Documents\Selecting skill\input\selection_rules.docx",
    "--provider",
    "deepseek",
    "--database",
    os.path.join(RUN_DIR, "curation.db"),
    "--artifacts-dir",
    os.path.join(RUN_DIR, "skill2_artifacts"),
    "--output",
    os.path.join(RUN_DIR, "02_financial_variable_curation", "directory_marked.xlsx"),
    "--overwrite",
]

sys.exit(cli.main(args))
