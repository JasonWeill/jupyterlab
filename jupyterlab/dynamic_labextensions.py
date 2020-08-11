# coding: utf-8
"""Utilities for installing Javascript extensions for the notebook"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import print_function

import json
import os
import os.path as osp
import shutil
import sys
import tarfile
import zipfile
from os.path import basename, join as pjoin, normpath
import subprocess

from urllib.parse import urlparse
from urllib.request import urlretrieve
from jupyter_core.paths import (
    jupyter_data_dir, jupyter_config_path, jupyter_path,
    SYSTEM_JUPYTER_PATH, ENV_JUPYTER_PATH,
)
from jupyter_core.utils import ensure_dir_exists
from ipython_genutils.py3compat import string_types, cast_unicode_py2
from ipython_genutils.tempdir import TemporaryDirectory
from jupyter_server.config_manager import BaseJSONConfigManager

from traitlets.utils.importstring import import_item

from .commands import build, AppOptions


DEPRECATED_ARGUMENT = object()

HERE = osp.abspath(osp.dirname(__file__))


#------------------------------------------------------------------------------
# Public API
#------------------------------------------------------------------------------

def develop_labextension(path, symlink=True, overwrite=False,
                        user=False, labextensions_dir=None,
                        destination=None, 
                        logger=None, sys_prefix=False
                        ):
    """Install a dynamic extension for JupyterLab
    
    Stages files and/or directories into the labextensions directory.
    By default, this compares modification time, and only stages files that need updating.
    If `overwrite` is specified, matching files are purged before proceeding.
    
    Parameters
    ----------
    
    path : path to file, directory, zip or tarball archive, or URL to install
        By default, the file will be installed with its base name, so '/path/to/foo'
        will install to 'labextensions/foo'. See the destination argument below to change this.
        Archives (zip or tarballs) will be extracted into the labextensions directory.
    user : bool [default: False]
        Whether to install to the user's labextensions directory.
        Otherwise do a system-wide install (e.g. /usr/local/share/jupyter/labextensions).
    overwrite : bool [default: False]
        If True, always install the files, regardless of what may already be installed.
    symlink : bool [default: True]
        If True, create a symlink in labextensions, rather than copying files.
        Windows support for symlinks requires a permission bit which only admin users
        have by default, so don't rely on it.
    labextensions_dir : str [optional]
        Specify absolute path of labextensions directory explicitly.
    destination : str [optional]
        name the labextension is installed to.  For example, if destination is 'foo', then
        the source file will be installed to 'labextensions/foo', regardless of the source name.
    logger : Jupyter logger [optional]
        Logger instance to use
    """
    # the actual path to which we eventually installed
    full_dest = None

    labext = _get_labextension_dir(user=user, sys_prefix=sys_prefix, labextensions_dir=labextensions_dir)
    # make sure labextensions dir exists
    ensure_dir_exists(labext)
    
    if isinstance(path, (list, tuple)):
        raise TypeError("path must be a string pointing to a single extension to install; call this function multiple times to install multiple extensions")
    
    path = cast_unicode_py2(path)

    if not destination:
        destination = basename(normpath(path))
    destination = cast_unicode_py2(destination)

    full_dest = normpath(pjoin(labext, destination))
    if overwrite and os.path.lexists(full_dest):
        if logger:
            logger.info("Removing: %s" % full_dest)
        if os.path.isdir(full_dest) and not os.path.islink(full_dest):
            shutil.rmtree(full_dest)
        else:
            os.remove(full_dest)

    # Make sure the parent directory exists
    os.makedirs(os.path.dirname(full_dest), exist_ok=True)

    if symlink:
        path = os.path.abspath(path)
        if not os.path.exists(full_dest):
            if logger:
                logger.info("Symlinking: %s -> %s" % (full_dest, path))
            os.symlink(path, full_dest)
        elif not os.path.islink(full_dest):
            raise ValueError("%s exists and is not a symlink" % path)

    elif os.path.isdir(path):
        path = pjoin(os.path.abspath(path), '') # end in path separator
        for parent, dirs, files in os.walk(path):
            dest_dir = pjoin(full_dest, parent[len(path):])
            if not os.path.exists(dest_dir):
                if logger:
                    logger.info("Making directory: %s" % dest_dir)
                os.makedirs(dest_dir)
            for file_name in files:
                src = pjoin(parent, file_name)
                dest_file = pjoin(dest_dir, file_name)
                _maybe_copy(src, dest_file, logger=logger)
    else:
        src = path
        _maybe_copy(src, full_dest, logger=logger)

    return full_dest


def develop_labextension_py(module, user=False, sys_prefix=False, overwrite=False, symlink=True, labextensions_dir=None, logger=None):
    """Develop a labextension bundled in a Python package.

    Returns a list of installed/updated directories.

    See develop_labextension for parameter information."""
    m, labexts = _get_labextension_metadata(module)
    base_path = os.path.split(m.__file__)[0]

    full_dests = []

    for labext in labexts:
        src = os.path.join(base_path, labext['src'])
        dest = labext['dest']
        if logger:
            logger.info("Installing %s -> %s" % (src, dest))

        full_dest = develop_labextension(
            src, overwrite=overwrite, symlink=symlink,
            user=user, sys_prefix=sys_prefix, labextensions_dir=labextensions_dir,
            destination=dest, logger=logger
            )
        full_dests.append(full_dest)

    return full_dests


def build_labextension(path, app_dir=None, logger=None):
    """Build a labextension in the given path"""
    # Ensure a staging directory but don't actually build anything.
    core_path = osp.join(HERE, 'staging')
    options = AppOptions(app_dir=app_dir, logger=logger)
    build(app_options=options, command="build:nobuild")
    staging_path = osp.join(options.app_dir, 'staging')
    builder = osp.join(staging_path, 'node_modules', '@jupyterlab', 'buildutils', 'lib', 'build-extension.js')

    path = os.path.abspath(path)
    if not osp.exists(osp.join(path, 'node_modules')):
        subprocess.check_call(['jlpm'], cwd=path)
    if logger:
        logger.info('Building extension in %s' % path)

    subprocess.check_call(['node', builder, '--core-path', core_path,  path], cwd=path)


def watch_labextension(path, app_dir=None, logger=None):
    """Watch a labextension in a given path"""
    # Ensure a staging directory but don't actually build anything.
    core_path = osp.join(HERE, 'staging')
    options = AppOptions(app_dir=app_dir, logger=logger)
    build(app_options=options, command="build:nobuild")
    staging_path = osp.join(options.app_dir, 'staging')
    builder = osp.join(staging_path, 'node_modules', '@jupyterlab', 'buildutils', 'lib', 'build-extension.js')
    
    path = os.path.abspath(path)
    if not osp.exists(osp.join(path, 'node_modules')):
        subprocess.check_call(['jlpm'], cwd=path)
    if logger:
        logger.info('Watching extension in %s' % path)


    subprocess.check_call(['node', builder, '--core-path', core_path,  '--watch', path], cwd=path)


#------------------------------------------------------------------------------
# Private API
#------------------------------------------------------------------------------


def _ensure_builder(logger=None):
    # Ensure staging from commands
    build(command=None)

    target = osp.join(get_app_dir(), 'extension_builder')
    if not osp.exists(osp.join(target, 'package.json')):
        if logger:
            logger.info('Generating extension builder in %s' % target)
        os.makedirs(osp.join(target))
        subprocess.check_call(["npm", "init", "-y"], cwd=target)
    
    core_path = osp.join(HERE, 'staging')
    with open(osp.join(core_path, 'package.json')) as fid:
        core_data = json.load(fid)
    
    # Make sure we have the latest deps
    target_package = osp.join(target, 'package.json')
    with open(target_package) as fid:
        package_data = json.load(fid)
    package_data['devDependencies'] = core_data['devDependencies']
    package_data['dependencies'] = core_data['dependencies']
    with open(target_package, 'w') as fid:
        json.dump(package_data, fid)
    subprocess.check_call(["npm", "install"], cwd=target)
    return osp.join(target, 'node_modules', '@jupyterlab', 'buildutils', 'lib', 'build-extension.js')
    

def _should_copy(src, dest, logger=None):
    """Should a file be copied, if it doesn't exist, or is newer?

    Returns whether the file needs to be updated.

    Parameters
    ----------

    src : string
        A path that should exist from which to copy a file
    src : string
        A path that might exist to which to copy a file
    logger : Jupyter logger [optional]
        Logger instance to use
    """
    if not os.path.exists(dest):
        return True
    if os.stat(src).st_mtime - os.stat(dest).st_mtime > 1e-6:
        # we add a fudge factor to work around a bug in python 2.x
        # that was fixed in python 3.x: https://bugs.python.org/issue12904
        if logger:
            logger.warn("Out of date: %s" % dest)
        return True
    if logger:
        logger.info("Up to date: %s" % dest)
    return False


def _maybe_copy(src, dest, logger=None):
    """Copy a file if it needs updating.

    Parameters
    ----------

    src : string
        A path that should exist from which to copy a file
    src : string
        A path that might exist to which to copy a file
    logger : Jupyter logger [optional]
        Logger instance to use
    """
    if _should_copy(src, dest, logger=logger):
        if logger:
            logger.info("Copying: %s -> %s" % (src, dest))
        shutil.copy2(src, dest)


def _get_labextension_dir(user=False, sys_prefix=False, prefix=None, labextensions_dir=None):
    """Return the labextension directory specified

    Parameters
    ----------

    user : bool [default: False]
        Get the user's .jupyter/labextensions directory
    sys_prefix : bool [default: False]
        Get sys.prefix, i.e. ~/.envs/my-env/share/jupyter/labextensions
    prefix : str [optional]
        Get custom prefix
    labextensions_dir : str [optional]
        Get what you put in
    """
    conflicting = [
        ('user', user),
        ('prefix', prefix),
        ('labextensions_dir', labextensions_dir),
        ('sys_prefix', sys_prefix),
    ]
    conflicting_set = ['{}={!r}'.format(n, v) for n, v in conflicting if v]
    if len(conflicting_set) > 1:
        raise ArgumentConflict(
            "cannot specify more than one of user, sys_prefix, prefix, or labextensions_dir, but got: {}"
            .format(', '.join(conflicting_set)))
    if user:
        labext = pjoin(jupyter_data_dir(), u'labextensions')
    elif sys_prefix:
        labext = pjoin(ENV_JUPYTER_PATH[0], u'labextensions')
    elif prefix:
        labext = pjoin(prefix, 'share', 'jupyter', 'labextensions')
    elif labextensions_dir:
        labext = labextensions_dir
    else:
        labext = pjoin(SYSTEM_JUPYTER_PATH[0], 'labextensions')
    return labext


def _get_labextension_metadata(module):
    """Get the list of labextension paths associated with a Python module.

    Returns a tuple of (the module path,             [{
        'src': 'mockextension',
        'dest': '_mockdestination'
    }])

    Parameters
    ----------

    module : str
        Importable Python module exposing the
        magic-named `_jupyter_labextension_paths` function
    """
    try:
        m = import_item(module)
    except Exception:
        m = None

    if not hasattr(m, '_jupyter_labextension_paths'):
        if osp.exists(osp.abspath(module)):
            from setuptools import find_packages
            packages = find_packages(module)
            if not packages:
                raise ValueError('Could not find module %s' % module)
            m = import_item(packages[0])

    if not hasattr(m, '_jupyter_labextension_paths'):
        raise KeyError('The Python module {} is not a valid labextension, '
                       'it is missing the `_jupyter_labextension_paths()` method.'.format(module))
    labexts = m._jupyter_labextension_paths()
    return m, labexts


if __name__ == '__main__':
    main()
