import re
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def style_document(doc):
    # Set default font
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    font.color.rgb = RGBColor(0x22, 0x22, 0x22)


def add_title(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(22)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)  # Navy Blue
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(12)


def add_h1(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(6)


def add_h2(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(13)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x2E, 0x6B, 0x9E)
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)


def add_h3(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(11.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)


def add_code_block(doc, code_text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.25)
    run = p.add_run(code_text)
    run.font.name = 'Consolas'
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def parse_markdown_to_docx(md_path: Path, docx_path: Path):
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    doc = Document()
    style_document(doc)

    in_code_block = False
    code_lines = []

    table_lines = []

    def flush_table():
        nonlocal table_lines
        if not table_lines:
            return
        
        # Parse markdown table
        rows_data = []
        for line in table_lines:
            parts = [c.strip() for c in line.strip().strip('|').split('|')]
            # check if separator line like :--- | :---
            if all(re.match(r'^:?-+:?$', p) for p in parts if p):
                continue
            rows_data.append(parts)
        
        if rows_data:
            num_cols = max(len(r) for r in rows_data)
            t = doc.add_table(rows=len(rows_data), cols=num_cols)
            t.style = 'Table Grid'
            for r_idx, row in enumerate(rows_data):
                for c_idx, cell_value in enumerate(row):
                    if c_idx < num_cols:
                        cell = t.cell(r_idx, c_idx)
                        cell.text = cell_value
                        if r_idx == 0:
                            for paragraph in cell.paragraphs:
                                for run in paragraph.runs:
                                    run.font.bold = True
                                    run.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
            doc.add_paragraph()
        table_lines = []

    for line in lines:
        stripped = line.strip()

        # Handle code blocks
        if stripped.startswith('```'):
            if in_code_block:
                in_code_block = False
                add_code_block(doc, '\n'.join(code_lines))
                code_lines = []
            else:
                flush_table()
                in_code_block = True
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(line.rstrip('\n'))
            continue

        # Handle tables
        if stripped.startswith('|') and stripped.endswith('|'):
            table_lines.append(stripped)
            continue
        else:
            flush_table()

        if not stripped:
            continue

        # Headings
        if stripped.startswith('# '):
            add_title(doc, stripped[2:].strip())
        elif stripped.startswith('## '):
            add_h1(doc, stripped[3:].strip())
        elif stripped.startswith('### '):
            add_h2(doc, stripped[4:].strip())
        elif stripped.startswith('#### '):
            add_h3(doc, stripped[5:].strip())
        elif stripped.startswith('* ') or stripped.startswith('- '):
            p = doc.add_paragraph(style='List Bullet')
            text = stripped[2:].strip()
            # Handle bold inside bullet
            parts = re.split(r'(\*\*.*?\*\*)', text)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)
            p.paragraph_format.space_after = Pt(2)
        elif re.match(r'^\d+\.\s+', stripped):
            match = re.match(r'^\d+\.\s+', stripped)
            p = doc.add_paragraph(style='List Number')
            text = stripped[match.end():].strip()
            parts = re.split(r'(\*\*.*?\*\*)', text)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)
            p.paragraph_format.space_after = Pt(2)
        elif stripped.startswith('---'):
            continue
        else:
            p = doc.add_paragraph()
            parts = re.split(r'(\*\*.*?\*\*)', stripped)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)
            p.paragraph_format.space_after = Pt(4)

    flush_table()
    doc.save(docx_path)
    print(f"Generated {docx_path}")


def main():
    doc_dir = Path("documentation")
    import shutil

    for md_file in doc_dir.glob("*.md"):
        docx_file = doc_dir / f"{md_file.stem}.docx"
        parse_markdown_to_docx(md_file, docx_file)
        
        # Also copy as .doc so both .doc and .docx exist
        doc_file = doc_dir / f"{md_file.stem}.doc"
        shutil.copyfile(docx_file, doc_file)
        print(f"Copied to {doc_file}")


if __name__ == "__main__":
    main()
