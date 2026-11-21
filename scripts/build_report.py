"""Build the course report, keeping teacher-provided front matter from the template.

Initial use: --template-docx /path/to/converted-template.docx
Subsequent builds reuse report/template_front_matter.json.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
from pathlib import Path
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report_content import CLASS, NAME, REFERENCES, REPO, STUDENT_ID, TITLE, abstracts, sections

STEM = f"{STUDENT_ID}_{NAME}_综合设计报告"


def font(run, size=12, east="宋体", latin="Times New Roman", bold=False):
    run.font.name = latin
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts"); rpr.insert(0, fonts)
    fonts.set(qn("w:eastAsia"), east)


def keep_rows(table):
    for row in table.rows:
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))


def set_cell(cell, text, size=10.5, bold=False):
    cell.text = str(text)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for p in cell.paragraphs:
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.first_line_indent = Pt(0)
        for r in p.runs:
            font(r, size=size, bold=bold)


def table(doc, rows, widths=None, size=10.5):
    tab = doc.add_table(rows=1, cols=len(rows[0]))
    tab.style = "Table Grid"
    tab.alignment = WD_TABLE_ALIGNMENT.CENTER
    tab.autofit = False
    for i, row in enumerate(rows):
        cells = tab.rows[0].cells if i == 0 else tab.add_row().cells
        for j, text in enumerate(row):
            set_cell(cells[j], text, size, i == 0)
            if widths:
                cells[j].width = Cm(widths[j])
    keep_rows(tab)
    return tab


def add_text(doc, text, style=None, centered=False, indent=True):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.first_line_indent = Pt(24 if indent and not centered else 0)
    if centered:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for part in re.split(r"(\[\d+\])", text):
        if not part:
            continue
        r = p.add_run(part); font(r)
        if re.fullmatch(r"\[\d+\]", part):
            r.font.superscript = True
            r.font.size = Pt(9)
    return p


def heading(doc, text, level=1):
    p = doc.add_paragraph(text, style=f"Heading {level}")
    p.paragraph_format.first_line_indent = Pt(0)
    return p


def page(doc, title, level=1):
    doc.add_page_break()
    return heading(doc, title, level)


def field(p, instruction, placeholder=""):
    run = p.add_run()
    begin = OxmlElement("w:fldChar"); begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = instruction
    sep = OxmlElement("w:fldChar"); sep.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t"); text.text = placeholder
    end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end")
    for el in [begin, instr, sep, text, end]:
        run._r.append(el)
    font(run, 10.5)


def configure_section(section, header=False, number_format=None, start=1):
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.8), Cm(2.2)
    section.left_margin = section.right_margin = Cm(2.5)
    section.header_distance = section.footer_distance = Cm(1.5)
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    hp, fp = section.header.paragraphs[0], section.footer.paragraphs[0]
    hp.clear(); fp.clear()
    if header:
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        font(hp.add_run("武汉工程大学计算机科学与工程学院  综合设计报告"), 10.5)
    if number_format:
        num = section._sectPr.find(qn("w:pgNumType"))
        if num is None:
            num = OxmlElement("w:pgNumType"); section._sectPr.append(num)
        num.set(qn("w:fmt"), number_format); num.set(qn("w:start"), str(start))
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        font(fp.add_run("- "), 10.5); field(fp, "PAGE"); font(fp.add_run(" -"), 10.5)


def template_profile(path):
    d = Document(path)
    tables = [[[c.text for c in row.cells] for row in t.rows] for t in d.tables]
    intro = "通过实训，考查学生的自学能力和应用深度学习相关课程知识的能力，使学生能够综合应用本专业学习到的数学、工程基础和智能科学与技术专业知识解决智能科学与技术领域的实际工程问题。锻炼学生针对实际问题，提出解决方案的能力。培养学生开发、选择与使用恰当的现代工具，设计完成智能科学与技术领域实际工程问题的能力。最后，还培养学生理解和评价智能科学与技术领域的专业工程实践对环境、社会可持续发展影响的意识。"
    return {"source_name": Path(path).name, "objective_intro": intro,
            "course_objectives": tables[0], "graduation_requirements": tables[1],
            "tasks": tables[3][0][0], "schedule": tables[4][0][0], "recommended_references": tables[4][1][0]}


def clean_teacher(s):
    return re.sub(r"[ \t]+", " ", s.replace("\n", "")).strip()


def front_matter(doc, profile):
    configure_section(doc.sections[0])
    for title, size in [("武汉工程大学", 26), ("计算机科学与工程学院", 22)]:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(12)
        font(p.add_run(title), size, "黑体", bold=True)
    doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("综合设计报告"), 30, "黑体", bold=True)
    p.paragraph_format.space_after = Pt(32)
    for label, text in [
        ("设计名称", "《人工智能编程基础》综合设计"), ("设计题目", TITLE), ("专业班级", CLASS),
        ("学生学号", STUDENT_ID), ("学生姓名", NAME), ("指导教师（职称）", "李晖（教授）"),
        ("学业导师（职称）", "________________"), ("学生成绩", "________________")]:
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(10)
        font(p.add_run(label+"："), 14, "黑体")
        font(p.add_run(text), 14)
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(14)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("完成时间：2026年10月11日—2026年12月13日"), 12)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("武汉工程大学计算机科学与工程学院 制"), 12)

    sec = doc.add_section(WD_SECTION_START.NEW_PAGE)
    configure_section(sec, number_format="lowerRoman")
    heading(doc, "说 明", 1)
    notes = [
        "报告中的第一、二、三项由综合设计负责人在综合设计开始前填写并发给每个学生。",
        "学业导师负责批改学生的设计报告，并给出相应的得分。同时，就设计报告质量撰写评语。",
        "指导教师就学生在设计期间的表现及设计完成情况分别给出相应的得分。同时，就此两项情况撰写评语。",
        "设计的总评成绩由上述各部分累加得出，由指导教师汇总，并填写于报告的封面。",
        "设计报告正文字数一般应不少于5000字，也可由综合设计负责人根据本项综合设计的具体情况酌情增加字数或内容。",
        "此表格式为武汉工程大学计算机科学与工程学院提供的基本格式（适用于学院各项课程设计），各专业也可根据本项综合设计的特点及内容做适当的调整，并上报学院批准。",
    ]
    for i, n in enumerate(notes, 1):
        add_text(doc, f"{i}、{n}")

    page(doc, "课程教学目标")
    add_text(doc, profile["objective_intro"])
    add_text(doc, "（一）课程目标", indent=False)
    table(doc, [[clean_teacher(c) for c in row] for row in profile["course_objectives"]], [.9, 7, 5, 3.1], 10.5)
    page(doc, "毕业要求与指标点")
    add_text(doc, "（二）所支撑的毕业要求及对应的指标点", indent=False)
    table(doc, [[clean_teacher(c) for c in row] for row in profile["graduation_requirements"]], [.9, 5.3, 4.5, 5.3], 10.5)

    page(doc, "成绩评定表")
    add_text(doc, f"学生姓名：{NAME}    学号：{STUDENT_ID}", indent=False)
    add_text(doc, "班级："+CLASS, indent=False)
    grade = [
        ["序号", "考核内容及权重", "课程目标", "评分标准", "评分人", "实际得分"],
        ["1", "工程知识\n20分", "课程目标1", "熟练运用数学、自然科学、工程基础和专业知识，解决实际工程问题。", "学业导师", ""],
        ["2", "设计开发解决方案\n30分", "课程目标2", "能够针对智能科学与技术领域的问题提出解决方案，设计满足特定需求的系统和模块。", "学业导师", ""],
        ["3", "使用现代工具\n40分", "课程目标3", "会使用Python软件开发语言，并能够运用集成开发环境，对涉及问题进行程序设计。", "指导老师", ""],
        ["4", "环境和可持续发展\n10分", "课程目标4", "能够理解复杂工程实践对环境、社会可持续发展的影响，并在报告有所体现。", "指导老师", ""],
    ]
    table(doc, grade, [.8, 2.5, 2, 7, 1.8, 1.9], 10.5)
    add_text(doc, "学业导师签字：________________    指导老师签字：________________", indent=False)
    add_text(doc, "总评成绩：________________", indent=False)

    for key, title in [("tasks", "一 综合设计任务要求"), ("schedule", "二 进度安排"), ("recommended_references", "三 资料与主要参考文献")]:
        page(doc, title)
        lines = profile[key].splitlines()
        # Preserve supplied first three sections, removing only empty placeholder lines.
        for line in lines[1:]:
            if line.strip():
                p = add_text(doc, line.strip(), indent=not bool(re.match(r"\s*(?:\d|\[|\(|集中|项目|实训)", line)))
                p.paragraph_format.line_spacing = 1.2
                p.paragraph_format.space_after = Pt(1)
                if line.strip().startswith("["):
                    for run in p.runs:
                        run.font.superscript = False
                        run.font.size = Pt(12)


def add_toc(doc):
    sec = doc.add_section(WD_SECTION_START.NEW_PAGE)
    configure_section(sec, header=True, number_format="upperRoman")
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("目 录"), 22, "黑体", bold=True)
    p = doc.add_paragraph()
    field(p, 'TOC \\o "1-2" \\h \\z \\u', "目录由文字处理软件更新")


def add_figure(doc, name, counters, chapter):
    titles = {
        "petal_distribution": ("花瓣测量值分布", "Distribution of petal measurements"),
        "network_architecture": ("网络结构与参数", "Network architecture and parameters"),
        "training_curves": ("训练及验证曲线", "Training and validation curves"),
        "confusion_matrix": ("测试集混淆矩阵", "Test set confusion matrix"),
        "baseline_comparison": ("相同划分下基线比较", "Baseline comparison on the same split"),
    }
    counters[chapter] = counters.get(chapter, 0)+1
    number = f"{chapter}-{counters[chapter]}"
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(ROOT/"figures"/(name+".png")), width=Cm(15.2 if name in ["training_curves", "network_architecture"] else 13.6))
    for caption in [f"图{number} {titles[name][0]}", f"Fig. {number} {titles[name][1]}"]:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = caption.startswith("图")
        font(p.add_run(caption), 10.5)


def data_tables(m, ex, prep):
    rows = {}
    rows["features"] = ("数据特征与标签", "Features and labels", [
        ["字段", "含义", "单位或编码"], ["sepal length", "花萼长度", "cm"], ["sepal width", "花萼宽度", "cm"],
        ["petal length", "花瓣长度", "cm"], ["petal width", "花瓣宽度", "cm"],
        ["class", "山鸢尾 变色鸢尾 维吉尼亚鸢尾", "0 1 2"]])
    rows["architecture"] = ("主网络逐层配置", "Main network configuration", [
        ["层", "输出维度", "激活", "可训练参数"], ["输入", "4", "—", "0"],
        ["隐藏层一", "16", "ReLU", "4×16+16=80"], ["隐藏层二", "8", "ReLU", "16×8+8=136"],
        ["输出层", "3", "Softmax", "8×3+3=27"], ["合计", "—", "—", "243"]])
    rows["scaler"] = ("训练集标准化参数", "Standardization fitted on training data", [
        ["特征", "均值 cm", "标准差 cm"],
        *[[n, f"{mu:.6f}", f"{s:.6f}"] for n, mu, s in zip(["花萼长", "花萼宽", "花瓣长", "花瓣宽"], prep["mean"], prep["scale"])]])
    rows["environment"] = ("实验环境与训练配置", "Environment and training settings", [
        ["项目", "配置或记录"], ["运行日期", "2026年11月22日"], ["CPU", "Intel Core i7-14650HX 单线程计算"],
        ["Python TensorFlow Keras", "3.10.12  2.20.0  3.12.4"], ["NumPy scikit learn", "2.2.6  1.7.2"],
        ["训练 验证 测试样本", "90  30  30"], ["Adam学习率 批大小", "0.01  16"],
        ["L2系数 最大轮数 早停耐心", "0.0001  400  35"],
        ["实际轮数 最低验证损失轮次", f"{m['epochs_run']}  {m['best_epoch']}"]])
    rows["classification"] = ("主模型各类别测试指标", "Classwise test metrics of the main model", [
        ["类别", "精确率", "召回率", "F1", "样本数"],
        *[[n, f"{m['classification_report'][n]['precision']:.4f}", f"{m['classification_report'][n]['recall']:.4f}", f"{m['classification_report'][n]['f1-score']:.4f}", "10"]
          for n in ["Iris-setosa", "Iris-versicolor", "Iris-virginica"]]])
    rows["errors"] = ("测试误判样本", "Misclassified test samples", [
        ["零基行号", "四项测量 cm", "真实类别", "预测类别", "最大分数"],
        ["134", "6.1 2.6 5.6 1.4", "virginica", "versicolor", "0.6486"],
        ["77", "6.7 3.0 5.0 1.7", "versicolor", "virginica", "0.9760"]])
    rows["baselines"] = ("测试集模型比较", "Model comparison on the test set", [
        ["方案", "准确率", "宏平均F1"], ["多数类", "33.33%", "0.1667"],
        ["逻辑回归", "93.33%", "0.9333"], ["两隐藏层神经网络", "93.33%", "0.9333"]])
    rows["ablations"] = ("仅使用验证集的变体比较", "Validation only ablation comparison", [
        ["方案", "参数数目", "验证准确率"], ["标准化双隐藏层主模型", "243", "93.33%"],
        ["不标准化双隐藏层", "243", "96.67%"], ["标准化单隐藏层", "67", "93.33%"]])
    return rows


def add_data_table(doc, key, counters, chapter, rows):
    counters[chapter] = counters.get(chapter, 0)+1
    num = f"{chapter}-{counters[chapter]}"
    zh, en, data = rows[key]
    for title in [f"表{num} {zh}", f"Table {num} {en}"]:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        font(p.add_run(title), 10.5)
    tab = table(doc, data, size=10.5)
    # Keep short analytical tables together; the larger teacher forms may span pages.
    for row in tab.rows[:-1]:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.keep_with_next = True
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def add_code(doc, code):
    for line in code.splitlines():
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.keep_together = True
        font(p.add_run(line if line else " "), size=8, east="宋体", latin="DejaVu Sans Mono")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-docx", type=Path)
    args = parser.parse_args()
    report_dir = ROOT/"report"
    report_dir.mkdir(exist_ok=True)
    profile_path = report_dir/"template_front_matter.json"
    if args.template_docx:
        profile_path.write_text(json.dumps(template_profile(args.template_docx), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    art = ROOT/"artifacts"
    m, ex, prep = [json.loads((art/f).read_text()) for f in ["metrics.json", "experiments.json", "preprocessing.json"]]
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Times New Roman", Pt(12)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
    normal.paragraph_format.line_spacing = 1.35
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.widow_control = True
    for level, size in [(1, 22), (2, 16), (3, 14)]:
        sty = doc.styles[f"Heading {level}"]
        sty.font.name, sty.font.size, sty.font.bold = "Times New Roman", Pt(size), True
        sty.font.color.rgb = RGBColor(0, 0, 0)
        sty._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "黑体")
        sty.paragraph_format.space_before = Pt(14)
        sty.paragraph_format.space_after = Pt(12)
        sty.paragraph_format.keep_with_next = True
        sty.paragraph_format.keep_together = True
        sty.paragraph_format.line_spacing = 1.25
        if level == 1:
            sty.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # Teacher forms must not appear in the report table of contents.
    front_matter(doc, profile)
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            p.style = doc.styles["Normal"]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.keep_with_next = True
            for run in p.runs:
                font(run, 18, "黑体", bold=True)
    add_toc(doc)
    cn, en = abstracts(m)
    page(doc, "摘 要")
    add_text(doc, cn)
    p = add_text(doc, "", indent=False)
    font(p.add_run("关键词："), 12, "黑体", bold=True)
    font(p.add_run("鸢尾花分类；多层感知机；TensorFlow；可复现性；可持续计算"), 12)
    page(doc, "Abstract")
    add_text(doc, en)
    p = add_text(doc, "", indent=False)
    font(p.add_run("Keywords: "), 12, "黑体", bold=True)
    font(p.add_run("Iris classification; multilayer perceptron; TensorFlow; reproducibility; sustainable computing"), 12)

    sec = doc.add_section(WD_SECTION_START.NEW_PAGE)
    configure_section(sec, header=True, number_format="decimal")
    blocks = sections(m, ex)
    figures, tables = {}, {}
    trows = data_tables(m, ex, prep)
    chapter = 0
    main_paragraphs=[]
    in_body = True
    for kind, text in blocks:
        if kind == "chapter":
            if chapter > 0:
                doc.add_page_break()
            if text.startswith("第"):
                chapter += 1
            else:
                in_body = False
            heading(doc, text)
        elif kind == "heading":
            heading(doc, text, 2)
        elif kind == "p":
            add_text(doc, text)
            if in_body:
                main_paragraphs.append(text)
        elif kind == "figure":
            add_figure(doc, text, figures, chapter)
        elif kind == "table":
            add_data_table(doc, text, tables, chapter, trows)
        elif kind == "code":
            add_code(doc, text)

    page(doc, "参考文献")
    for i, ref in enumerate(REFERENCES, 1):
        p = add_text(doc, f"[{i}] {ref}", indent=False)
        for r in p.runs:
            r.font.superscript = False
            r.font.size = Pt(12)
        p.paragraph_format.line_spacing = 1.25
        p.paragraph_format.space_after = Pt(7)

    page(doc, "附录 主要程序代码")
    add_text(doc, "附录列出数据划分、建模、训练和预测的核心函数。包含导入、常量、命令行及结果保存的完整可执行程序位于仓库src/iris_classifier.py。", indent=False)
    add_text(doc, "项目地址："+REPO, indent=False)
    source = (ROOT/"src/iris_classifier.py").read_text()
    tree = ast.parse(source)
    selected = ["load_data", "split_indices", "build_model", "make_dataset", "fit_network", "validate_measurements", "predict"]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in selected:
            p = add_text(doc, node.name, indent=False)
            p.paragraph_format.keep_with_next = True
            add_code(doc, ast.get_source_segment(source, node))
            doc.add_paragraph()
    page(doc, "附录 复现与成果索引")
    add_text(doc, "安装主要依赖后，使用以下命令复现。报告构建还需requirements-dev.txt中的python-docx；PDF导出与目录更新使用LibreOffice。", indent=False)
    add_code(doc, "python -m venv .venv\nsource .venv/bin/activate\npip install -r requirements-dev.txt\npython -m src.iris_classifier train\npython scripts/make_figures.py\npython scripts/build_report.py\npython -m pytest -q")
    table(doc, [["成果", "位置"], ["源程序与自动化检查", "src/  tests/"], ["原始数据与署名", "data/iris.csv  data/ATTRIBUTION.txt"],
        ["网络与预处理参数", "artifacts/iris_mlp.keras  preprocessing.json"], ["指标与逐条预测", "artifacts/metrics.json  test_predictions.csv"],
        ["索引与训练记录", "artifacts/split_indices.json  history.csv"], ["基线与验证扩展实验", "artifacts/experiments.json"],
        ["图表和报告", "figures/  report/"], ["仓库", REPO]])
    add_text(doc, "本次数据CSV的SHA256：", indent=False)
    add_code(doc, m["data_sha256"][:32]+"\n"+m["data_sha256"][32:])
    stats = {"main_body_chinese_characters_excluding_abstracts_tables_captions_summary_appendix": len(re.findall(r"[\u4e00-\u9fff]", "".join(main_paragraphs))),
        "abstract_chinese_characters": len(re.findall(r"[\u4e00-\u9fff]", cn)), "references": len(REFERENCES),
        "figures": sum(figures.values()), "tables_in_body": sum(tables.values()), "student": NAME, "student_id": STUDENT_ID}
    assert stats["main_body_chinese_characters_excluding_abstracts_tables_captions_summary_appendix"] >= 5000
    assert stats["abstract_chinese_characters"] >= 300
    (report_dir/"validation.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    doc.core_properties.title = TITLE
    doc.core_properties.author = NAME
    doc.core_properties.subject = "《人工智能编程基础》综合设计"
    doc.core_properties.keywords = "鸢尾花 TensorFlow 综合设计"
    out = report_dir/(STEM+".docx")
    doc.save(out)
    print(out)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
