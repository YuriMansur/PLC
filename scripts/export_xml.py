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
    # recursive=True — POU/FB выгружается ЦЕЛИКОМ: тело + ВСЕ методы/свойства/
    # действия вложены в ОДИН файл. Так файл самодостаточен и импортируется в
    # Application одним вызовом (Replace создаёт FB сразу со всеми методами).
    # (Прежний вывод «recursive=True теряет методы» был ложным — он получен на
    #  ИСПОРЧЕННОМ проекте, где у FB реально оставалось по 1 методу.)
    proj.export_xml([obj], path, True)
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


def _is_container(node, children):
    """Узел, в который НАДО спускаться (а не экспортировать целиком): папка,
    устройство, приложение — или узел-обёртка над ними (напр. 'Plc Logic',
    чей ребёнок — Application). POU/DUT/GVL контейнерами НЕ считаются.

    ВАЖНО: по детям проверяем ТОЛЬКО application/device, а НЕ is_folder. У FB
    бывают ВНУТРЕННИЕ папки методов (напр. SM3ServoDriver → Private/Public,
    TimeManager → DateAndTime/TaskData). Если считать FB контейнером из-за такой
    папки — спустимся внутрь и наделаем битых per-method файлов, а методы не
    соберутся. FB должен уйти ОДНИМ файлом (recursive=True вложит и папки методов).

    children — снимок get_children (см. _walk)."""
    if (getattr(node, "is_folder", False) or getattr(node, "is_device", False)
            or getattr(node, "is_application", False)):
        return True
    for c in children:
        if getattr(c, "is_application", False) or getattr(c, "is_device", False):
            return True
    return False


def _walk(proj, node, out_dir, parts):
    """Обход дерева:
      - папка/устройство/приложение → сам не объект кода, ТОЛЬКО спускаемся внутрь;
      - POU/FB/DUT/GVL              → экспортируем ЦЕЛИКОМ (recursive=True) одним
                                      файлом и в его дети-методы НЕ спускаемся —
                                      они уже вложены в этот файл.

    Один файл = один самодостаточный POU/FB со всеми методами. Это импортируется
    в Application одним вызовом. (Раскладка «метод = отдельный файл» не годится:
    каждый такой файл содержит полную обёртку родительского FB и не импортируется
    ни в FB, ни плоско в Application.)

    Код живёт не только под Application (напр. проектные GVL в папке 'ГОСТ'),
    поэтому обход не ограничиваем поддеревом Application."""
    name = node.get_name(False)
    children = list(node.get_children(False))
    if _is_container(node, children):
        # чистый контейнер — только спускаемся внутрь
        for child in children:
            _walk(proj, child, out_dir, parts + [name])
        return
    if _is_code_container(node):
        # POU/FB целиком (методы вложены recursive=True) — в детей НЕ спускаемся
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
