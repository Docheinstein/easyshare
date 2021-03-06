# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))


# -- Project information -----------------------------------------------------

project = 'easyshare'
copyright = '2020, Stefano Dottore'
author = 'Stefano Dottore'

# The full version, including alpha/beta/rc tags
release = "0.13"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",  # avoid to use reST syntax
    "sphinx_rtd_theme",     # read the docs theme
    "recommonmark"
]

# Add any paths that contain templates here, relative to this directory.
# templates_path = ['_templates']

# List of patterns, relative to server directory, that match files and
# directories to ignore when looking for server files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

source_suffix = {
    '.rst': 'restructuredtext',
    '.txt': 'markdown',
    '.md': 'markdown',
    '.MD': 'markdown',
}

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
# html_static_path = ['_static']
#
# This value determines how to group the document tree into manual pages.
# It must be a list of tuples (startdocname, name, description, authors, section), where the items are:
#
# startdocname
#     String that specifies the document name of the manual page’s master document.
#     All documents referenced by the startdoc document in TOC trees will be included in the manual file.
#     (If you want to use the default master document for your manual pages build, use your master_doc here.)
# name
#     Name of the manual page. This should be a short string without spaces or special characters.
#     It is used to determine the file name as well as the name of the manual page (in the NAME section).
# description
#     Description of the manual page. This is used in the NAME section.
# authors
#     A list of strings with authors, or a single string.
#     Can be an empty string or list if you do not want to automatically generate an AUTHORS section in the manual page.
# section
#
#     The manual page section. Used for the output file name as well as in the manual page header.

man_pages = [
    # man 1 es
    (
        "es",
        'es',
        'client of the easyshare application',
        [author],
        1
    ),
    # man 1 esd
    (
        "esd",
        'esd',
        'server of the easyshare application',
        [author],
        1
    ),
    # man 1 es-tools
    (
        "es-tools",
        'es-tools',
        'tools for administrators of easyshare servers',
        [author],
        1
    )
]