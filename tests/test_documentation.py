from __future__ import annotations

import struct
import unittest
import xml.etree.ElementTree as ET

from project_support import REPO_ROOT


class DocumentationTests(unittest.TestCase):
    diagram = REPO_ROOT / "docs" / "diagrams" / "skillforge-lifecycle"

    def test_readme_embeds_the_rendered_lifecycle_diagram(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "docs/diagrams/skillforge-lifecycle.svg",
            readme,
        )
        self.assertIn("Personas swap. Verticals add.", readme)
        self.assertIn("Windows PowerShell", readme)

    def test_editable_diagram_sources_are_present_and_well_formed(self) -> None:
        mermaid = self.diagram.with_suffix(".mmd").read_text(encoding="utf-8")
        plantuml = self.diagram.with_suffix(".puml").read_text(encoding="utf-8")
        d2 = self.diagram.with_suffix(".d2").read_text(encoding="utf-8")
        ascii_diagram = self.diagram.with_suffix(".txt").read_text(encoding="utf-8")

        self.assertTrue(mermaid.startswith("flowchart"))
        self.assertTrue(plantuml.startswith("@startuml"))
        self.assertTrue(plantuml.rstrip().endswith("@enduml"))
        self.assertIn("direction: down", d2)
        for stage in (
            "CONTRIBUTORS DEFINE INTENT",
            "CANONICAL SKILLFORGE REPOSITORY",
            "BUILD AND QUALITY PIPELINE",
            "GENERATED DISTRIBUTION",
            "HOST-SPECIFIC DELIVERY",
        ):
            self.assertIn(stage, ascii_diagram)

        drawio = ET.parse(self.diagram.with_suffix(".drawio")).getroot()
        svg = ET.parse(self.diagram.with_suffix(".svg")).getroot()
        self.assertEqual(drawio.tag, "mxfile")
        self.assertEqual(svg.tag.rsplit("}", 1)[-1], "svg")

    def test_rendered_diagram_assets_have_real_file_signatures(self) -> None:
        png = self.diagram.with_suffix(".png").read_bytes()
        pdf = self.diagram.with_suffix(".pdf").read_bytes()

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(png), 100_000)
        self.assertGreater(len(pdf), 100_000)

    def test_social_preview_has_github_dimensions_and_size(self) -> None:
        source = (
            REPO_ROOT / "docs" / "social-preview" / "skillforge-social-preview.svg"
        )
        rendered = source.with_suffix(".png")

        self.assertEqual(
            ET.parse(source).getroot().tag.rsplit("}", 1)[-1],
            "svg",
        )
        png = rendered.read_bytes()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (1280, 640))
        self.assertLess(len(png), 1_000_000)


if __name__ == "__main__":
    unittest.main()
