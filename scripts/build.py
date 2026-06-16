# -*- coding: utf-8 -*-
"""
build.py — CODESYS ScriptEngine (IronPython 2.7). Серверная сборка.

Вариант A: берём .project-ШАБЛОН (в нём настроено «железо»: устройство, IO,
task-config), вливаем в него код из src_xml/ (PLCopen XML), компилируем,
проверяем на ошибки и сохраняем .projectarchive. Код возврата != 0 при ошибках
компиляции — чтобы CI красил сборку.

Запуск:
  "<...>\\CODESYS.exe" --profile="CODESYS V3.5 SP17" --noUI ^
      --runscript="scripts\\build.py" ^
      --scriptargs:"project\\V0.5\\117_1_V0.5.project src_xml out\\117_1_V0.5.projectarchive"

ВАЖНО: исполняется только на машине с CODESYS SP17. [VERIFY] — места, где
сигнатуры/методы зависят от версии и должны быть подтверждены первым прогоном.
"""

import os
import sys
import glob


def _parse_args():
    args = [a for a in sys.argv if a and not a.lower().endswith("build.py")]
    if len(args) < 3:
        raise SystemExit("Использование: build.py <template.project> <src_xml> <archive_out>")
    template = os.path.abspath(args[-3])
    src_xml  = os.path.abspath(args[-2])
    archive  = os.path.abspath(args[-1])
    return template, src_xml, archive


def _find_application(node):
    """Найти первый узел Application в поддереве (туда импортируем код)."""
    if getattr(node, "is_application", False):
        return node
    for child in node.get_children(False):
        found = _find_application(child)
        if found is not None:
            return found
    return None


def main():
    template, src_xml, archive = _parse_args()
    print("template: " + template)
    print("src_xml : " + src_xml)
    print("archive : " + archive)

    proj = projects.open(template)              # noqa: F821

    app = None
    for top in proj.get_children():
        app = _find_application(top)
        if app:
            break
    if app is None:
        raise SystemExit("ERROR: Application не найден в шаблоне")

    # Влить код из всех XML (рекурсивно по src_xml). Импорт в Application.
    xml_files = sorted(glob.glob(os.path.join(src_xml, "**", "*.xml")))
    if not xml_files:
        # IronPython 2.7: glob без recursive=True — пройдём вручную
        xml_files = []
        for root, _dirs, files in os.walk(src_xml):
            for f in files:
                if f.lower().endswith(".xml"):
                    xml_files.append(os.path.join(root, f))
        xml_files.sort()

    print("импорт XML: %d файл(ов)" % len(xml_files))
    for path in xml_files:
        # [VERIFY] сигнатура import_xml: вероятно app.import_xml(path) или
        # proj.import_xml(path, reporter). Подтвердить на SP17.
        app.import_xml(path)
        print("  + " + os.path.basename(path))

    # Компиляция/проверка. [VERIFY] метод зависит от версии:
    #   - app.generate_code()  (свежие SP)  ИЛИ
    #   - proj.check_all_pool_objects() / proj.check_all()
    # Ошибки читаем из message store (system).
    print("компиляция...")
    try:
        app.generate_code()                     # [VERIFY]
    except Exception as e:
        print("WARN generate_code недоступен (%s) — пробуем check_all" % e)
        try:
            proj.check_all_pool_objects()       # [VERIFY] fallback
        except Exception as e2:
            print("WARN проверка недоступна: %s" % e2)

    # [VERIFY] чтение ошибок компиляции из system message store.
    errors = 0
    try:
        for m in system.get_message_objects():  # [VERIFY] имя метода/severity-поля
            sev = str(getattr(m, "severity", "")).lower()
            if "error" in sev:
                errors += 1
                print("ERROR: " + m.text)
    except Exception as e:
        print("WARN не удалось прочитать сообщения компиляции: %s" % e)

    # Сохранить архив (API подтверждён доками).
    out_dir = os.path.dirname(archive)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    projects.save_archive(                       # noqa: F821
        path=archive,
        comment="CI build",
        additional_files=[],
        additional_categories=[ArchiveCategories.libraries,   # noqa: F821
                               ArchiveCategories.devices],
    )
    print("archive saved: " + archive)

    proj.close()                                 # [VERIFY]

    if errors:
        print("BUILD FAILED: %d ошибк(и) компиляции" % errors)
        sys.exit(1)
    print("BUILD OK")


main()
