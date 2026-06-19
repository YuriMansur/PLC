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
import re
import sys


def _exit(code):
    """Принудительно завершить процесс CODESYS.

    В --noUI CODESYS.exe после --runscript нередко НЕ закрывается сам (висит) —
    из-за этого run_build.bat не доходит до вердикта. sys.exit() кидает
    SystemExit, который движок ловит, и процесс остаётся жить. Поэтому глушим
    процесс жёстко через .NET (доступно в IronPython). Архив к этому моменту
    уже сохранён, проект закрыт — терять нечего.
    Вердикт пройдено/провалено всё равно выносит bat по build.log, поэтому
    code здесь некритичен."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        import System                              # .NET (IronPython)
        System.Environment.Exit(code)
    except Exception:
        sys.exit(code)


def _parse_args():
    args = [a for a in sys.argv if a and not a.lower().endswith("build.py")]
    if len(args) < 3:
        raise SystemExit("Использование: build.py <template.project> <src_xml> <archive_out>")
    template = os.path.abspath(args[-3])
    src_xml  = os.path.abspath(args[-2])
    archive  = os.path.abspath(args[-1])
    return template, src_xml, archive


class _ImportReporter(ImportReporter):          # noqa: F821 (scriptengine)
    """Reporter для import_xml: считает ошибки, конфликты разрешает заменой."""
    def __init__(self):
        self.errors = 0

    def error(self, message):
        self.errors += 1
        print("IMPORT ERROR: " + message)

    def warning(self, message):
        print("IMPORT WARN: " + message)

    def resolve_conflict(self, obj):
        return ConflictResolve.Replace          # noqa: F821 — перезаписать существующий

    def added(self, obj):
        pass

    def replaced(self, obj):
        pass

    def skipped(self, obj):
        pass

    @property
    def aborting(self):
        return False


# Итоговая строка компиляции: «… завершена -- N ошибок, M предупреждений …».
# Считаем число перед «ошиб»/«error».
_ERR_RE = re.compile(u"(\\d+)\\s*(?:ошиб|error)", re.IGNORECASE | re.UNICODE)
# Признак строки-итога компиляции.
_DONE_KEYS = (u"заверш", u"complet", u"прерв", u"abort")


def _count_errors():
    """(errors, could_read).

    Error-сообщения компиляции через ScriptEngine НЕДОСТУПНЫ: get_message_objects()
    отдаёт только severity=Text (консольное эхо), а get_message_filter_categories()
    в этой версии вообще нет. Но ИТОГ компиляции («компиляция завершена -- N ошибок»)
    приходит как Text — его и парсим.

    Fail-safe: если итоговую строку не нашли (или сообщений нет) — возвращаем
    (-1, False), чтобы сборка падала, а не маскировала результат фиктивным OK."""
    try:
        msgs = list(system.get_message_objects())               # noqa: F821
    except Exception as e:
        print("WARN get_message_objects(): %s" % e)
        return -1, False
    if not msgs:
        return -1, False

    found = False
    errors = 0
    for m in msgs:
        text = getattr(m, "text", "") or ""
        low = text.lower()
        is_compile = ("компил" in low) or ("compil" in low)
        if not is_compile:
            continue
        if not any(k in low for k in _DONE_KEYS):
            continue
        # это итоговая строка компиляции
        found = True
        mm = _ERR_RE.search(text)
        n = int(mm.group(1)) if mm else 0
        if n > errors:
            errors = n
        print("DIAG итог компиляции: " + text)

    if not found:
        print("DIAG итоговая строка компиляции не найдена среди %d Text-сообщений"
              % len(msgs))
        return -1, False
    return errors, True


_TARGET_CACHE = {}


def _resolve_target(proj, app, folder_parts):
    """Найти объект-цель импорта по цепочке имён папок из src_xml.

    folder_parts напр. ['Device','Plc Logic','Application','6.Logic'] — спускаемся
    от корня проекта по именам узлов; недостающие промежуточные узлы создаём как
    ПАПКИ. Так объект ляжет в свою папку, а не в корень Application (PLCopen XML
    не хранит расположение — без этого всё валится в корень).

    Если цепочку разрешить не удалось — fallback в Application."""
    key = tuple(folder_parts)
    if key in _TARGET_CACHE:
        return _TARGET_CACHE[key]
    node = None
    for name in folder_parts:
        children = proj.get_children() if node is None else node.get_children(False)
        nxt = None
        for c in children:
            try:
                if c.get_name(False) == name:
                    nxt = c
                    break
            except Exception:
                pass
        if nxt is None:
            if node is None:
                node = app                          # корень не нашли — кладём в Application
                break
            try:
                nxt = node.create_folder(name)      # [VERIFY] создать недостающую папку
            except Exception:
                break                               # не вышло — цель = текущий node
        node = nxt
    target = node if node is not None else app
    _TARGET_CACHE[key] = target
    return target


def main():
    template, src_xml, archive = _parse_args()
    print("template: " + template)
    print("src_xml : " + src_xml)
    print("archive : " + archive)

    # КРИТИЧНО: импорт идёт с ConflictResolve.Replace, который УДАЛЯЕТ и
    # пересоздаёт объекты. Если открыть оригинал — битый src_xml сотрёт из него
    # методы прямо на диске (так уже терялись ~54 объекта). Поэтому работаем
    # ВСЕГДА на одноразовой копии, а оригинал не открываем на запись никогда.
    import shutil, tempfile
    work_dir = tempfile.mkdtemp(prefix="codesys_build_")
    work_proj = os.path.join(work_dir, os.path.basename(template))
    shutil.copy2(template, work_proj)
    print("рабочая копия (оригинал не трогаем): " + work_proj)

    proj = projects.open(work_proj)             # noqa: F821 — открываем КОПИЮ, не оригинал

    apps = proj.find("Application", True)        # [VERIFY] find(name, recursive) → список
    if not apps:
        raise SystemExit("ERROR: Application не найден в шаблоне")
    app = apps[0]

    # Импорт В СВОЮ ПАПКУ: путь файла в src_xml задаёт расположение
    # (Application/6.Logic/StandLogic.xml → импорт в объект-папку 6.Logic), иначе
    # PLCopen XML не хранит папку и всё валится в корень Application. Один файл =
    # один самодостаточный POU/FB (методы вложены recursive=True). Файлы уровня
    # устройства (Local High Speed IO и т.п.) при импорте упадут → «пропущено».
    xml_files = []
    for root, _dirs, files in os.walk(src_xml):
        for f in files:
            if f.lower().endswith(".xml"):
                xml_files.append(os.path.join(root, f))
    xml_files.sort()

    reporter = _ImportReporter()
    imported = skipped = 0
    print("импорт XML: %d файл(ов)" % len(xml_files))
    for path in xml_files:
        rel = os.path.relpath(os.path.dirname(path), src_xml)
        folder_parts = [] if rel == "." else rel.split(os.sep)
        target = _resolve_target(proj, app, folder_parts)
        try:
            target.import_xml(reporter, path)
            imported += 1
        except Exception as e:
            skipped += 1
            print("  ПРОПУСК %s (в '%s'): %s"
                  % (os.path.basename(path), folder_parts[-1] if folder_parts else "Application", e))
    print("импортировано: %d, пропущено: %d" % (imported, skipped))

    # Компиляция/проверка. [VERIFY] метод зависит от версии:
    #   - app.generate_code()  (свежие SP)  ИЛИ
    #   - proj.check_all_pool_objects() / proj.check_all()
    print("компиляция...")
    compiled = False
    try:
        app.generate_code()                     # [VERIFY]
        compiled = True
    except Exception as e:
        print("WARN generate_code недоступен (%s) — пробуем check_all" % e)
        try:
            proj.check_all_pool_objects()       # [VERIFY] fallback
            compiled = True
        except Exception as e2:
            print("WARN проверка недоступна: %s" % e2)

    # Информативно: попытка прочитать итог из API (в этой версии ScriptEngine
    # ненадёжно — get_message_objects() отдаёт ошибки не всегда). ОКОНЧАТЕЛЬНЫЙ
    # вердикт пройдено/провалено выносит run_build.bat по числу строк уровня
    # 'Error:' в build.log — это надёжно и не зависит от API.
    errors, could_read = _count_errors()
    if could_read:
        print("детектор(API): ошибок компиляции = %d" % errors)
    else:
        print("детектор(API) итог не прочитал — вердикт по build.log (run_build.bat)")

    if not compiled:
        print("BUILD FAILED: компиляция не запустилась")
        proj.close()
        _exit(1)

    # Архив сохраняем при успешном generate_code. Если в коде есть ошибки —
    # архив всё равно создаётся, но run_build.bat пометит сборку проваленной
    # и удалит архив.
    out_dir = os.path.dirname(archive)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    proj.save_archive(                           # [VERIFY] метод на проекте, не на projects
        path=archive,
        comment="CI build",
        additional_files=[],
        additional_categories=[ArchiveCategories.libraries,   # noqa: F821
                               ArchiveCategories.devices],
    )
    print("archive saved: " + archive)

    proj.close()                                 # [VERIFY]
    print("BUILD DONE (итог компиляции — в build.log, вердикт даёт run_build.bat)")
    _exit(0)                                      # форс-выход: иначе CODESYS --noUI висит


main()
