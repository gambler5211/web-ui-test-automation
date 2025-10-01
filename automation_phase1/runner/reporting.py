from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional


class JUnitWriter:
    """Writer for JUnit XML test results."""
    
    @staticmethod
    def write(path: Path, suite_name: str, results: List[Dict[str, Any]]) -> None:
        """Write JUnit XML with test results."""
        # Create test suite
        testsuite = ET.Element("testsuite")
        testsuite.set("name", suite_name)
        testsuite.set("tests", str(len(results)))
        
        # Count failures
        failures = sum(1 for r in results if r.get("error"))
        testsuite.set("failures", str(failures))
        testsuite.set("errors", "0")
        total_ms = sum(r.get("duration_ms", 0) for r in results)
        testsuite.set("time", str(round(total_ms / 1000.0, 4)))
        
        for result in results:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", result["name"])
            testcase.set("classname", suite_name)
            testcase.set("time", str(round(result.get("duration_ms", 0) / 1000.0, 4)))
            
            if result.get("error"):
                failure = ET.SubElement(testcase, "failure")
                failure.set("message", str(result["error"]))
                body_lines = [
                    str(result.get("traceback", "")).strip(),
                ]
                if result.get("screenshot"):
                    body_lines.append(f"Screenshot: {result['screenshot']}")
                if result.get("url"):
                    body_lines.append(f"URL: {result['url']}")
                failure.text = "\n".join([l for l in body_lines if l])
        
        # Write XML file
        tree = ET.ElementTree(testsuite)
        ET.indent(tree, space="  ", level=0)
        tree.write(path, encoding="utf-8", xml_declaration=True)
