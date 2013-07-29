from setuptools import setup, find_packages
import sys, os

version = '1.0.10'

setup(name="holland",
      version=version,
      description="Holland Core Plugins",
      long_description="""\
      These are the plugins required for basic Holland functionality.
      """,
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords="",
      author="Rackspace",
      author_email="holland-devel@googlegroups.com",
      url='http://www.hollandbackup.org/',
      license="3-Clause BSD",
      packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
      include_package_data=True,
      zip_safe=True,
      test_suite='tests',
      install_requires=[
        # 'configobj' # currently this is bundled internally
      ],
      entry_points="""
      # Scripts generated by setuptools
      [console_scripts]
      holland = holland.core.cmdshell:main

      # Holland subcommands
      [holland.commands]
      help = holland.commands.help:Help
      listplugins = holland.commands.list_plugins:ListPlugins
      listbackups = holland.commands.list_backups:ListBackups
      backup = holland.commands.backup:Backup
      mk-config = holland.commands.mk_config:MkConfig
      purge = holland.commands.purge:Purge
      #restore = holland.commands.restore:Restore
      """,
      namespace_packages=['holland', 'holland.backup', 'holland.lib', 'holland.commands'],
      )
