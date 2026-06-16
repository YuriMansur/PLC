# -*- coding: utf-8 -*-
"""
export_xml.py — CODESYS ScriptEngine (IronPython 2.7).

Экспортирует КОД проекта (POU/DUT/GVL и т.п.) в PLCopen XML — по одному файлу
на объект, чтобы в git были читаемые диффы вместо бинарного .project.

Вариант A: «железо» (устройство, IO-маппинг, task-config) НЕ экспортируется —
оно живёт в .project-шаблоне. Здесь выгружается только содержимое Application'ов.

Запуск (из bat/хука):
  "<...>\\CODESYS.exe" --profile="CODESYS V3.5 SP17" --noUI ^
      --runscript="scripts\\export_xml.py" ^
      --scriptargs:"project\\V0.5\\117_1_V0.5.project src_xml"

ВАЖНО: точные сигнатуры export_xml/get_children сверены по докам, но запускать
и проверять надо на машине с CODESYS SP17 (здесь исполнить нельзя). Места,
которые могут отличаться по версии, помечены [VERIFY].
"""

import os
import re
import shutil
import sys

# creationDateTime в шапке PLCopen XML = время экспорта (меняется каждый прогон).
# Зануляем его, иначе git видит все файлы изменёнными на каждом коммите.
_CREATION_RE = re.compile(r'creationDateTime="[^"]*"')
_CREATION_FIXED = 'creationDateTime="1970-01-01T00:00:00"'

# scriptengine доступен неявно: при старте скрипта CODESYS делает
# `from scriptengine import *` (projects, ArchiveCategories и т.д.).


def _parse_args():
    # sys.argv содержит то, что передано в --scriptargs:"...":  [project, out_dir]
    args = [a for a in sys.argv if a and not a.lower().endswith("export_xml.py")]
    if len(args) < 2:
        raise SystemExit("Использование: export_xml.py <project.project> <out_dir>")
    project_path = os.path.abspath(args[-2])
    out_dir      = os.path.abspath(args[-1])
    return project_path, out_dir


def _is_code_container(obj):
    """True для узлов, в которые надо спускаться/которые экспортировать как код.
    Пропускаем «железо»: устройство и (если доступно) задачи."""
    # [VERIFY] набор is_* зависит от версии; is_device есть точно.
    if getattr(obj, "is_device", False):
        return False
    if getattr(obj, "is_task", False):
        return False
    return True


def _safe_name(name):
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in name).strip()


def _export_object(proj, obj, out_dir, parts):
    """Экспортировать один объект в <out_dir>/<путь-в-дереве>.xml."""
    rel = os.path.join(*[_safe_name(p) for p in parts]) if parts else _safe_name(obj.get_name(False))
    path = os.path.join(out_dir, rel + ".xml")
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    # [VERIFY] сигнатура: export_xml(objects, path, recursive)
    proj.export_xml([obj], path, False)
    _normalize(path)
    print("export: " + rel + ".xml")


def _normalize(path):
    """Убрать летучий creationDateTime, чтобы диффы были только по реальным изменениям."""
    with open(path, "rb") as f:
        text = f.read().decode("utf-8")
    fixed = _CREATION_RE.sub(_CREATION_FIXED, text)
    if fixed != text:
        with open(path, "wb") as f:
            f.write(fixed.encode("utf-8"))


def _walk(proj, node, out_dir, parts):
    """Рекурсивный обход: листовые объекты → отдельные XML, папки → структура.

    Экспортируем ВСЁ, кроме устройства/задач (is_device/is_task). Код проекта
    живёт не только под Application (напр. проектные GVL в папке 'ГОСТ'),
    поэтому ограничивать обход поддеревом Application нельзя — потеряем код."""
    name = node.get_name(False)
    children = node.get_children(False)   # False = только прямые потомки
    if children:
        for child in children:
            _walk(proj, child, out_dir, parts + [name])
    elif _is_code_container(node):
        _export_object(proj, node, out_dir, parts + [name])


def main():
    project_path, out_dir = _parse_args()
    print("project : " + project_path)
    print("out_dir : " + out_dir)

    # Чистим прошлый экспорт, чтобы удалённые POU не оставались «призраками» в git
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    proj = projects.open(project_path)          # noqa: F821 (scriptengine)
    try:
        for top in proj.get_children():
            _walk(proj, top, out_dir, [])
    finally:
        # Экспорт ничего не меняет в проекте — закрываем без сохранения.
        proj.close()                            # [VERIFY] метод close() на проекте
    print("DONE")


main()
