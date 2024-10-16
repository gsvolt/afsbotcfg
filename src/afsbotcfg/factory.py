# Copyright (c) 2019 Sine Nomine Associates
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.


"""OpenAFS buildbot build factories.

This module provides the factories which create the OpenAFS build steps.
Build factories are specified by class name in the master.cfg.j2 template.

Classes:

    GerritCheckoutFactory: Base class for our build factories.

    UnixBuildFactory:      Build with autoconf and make. Optionally
                           render documents and run TAP unit tests.

    WindowsBuildFactory:   Build on Windows using a preinstalled script.

    ELRpmBuildFactory:     Build RPM packages on a RedHat-like builder.
                           This factory also builds the kernel module from the
                           generated DMKS package to verify the DKMS package.
"""


from buildbot.plugins import steps
from buildbot.plugins import util

from afsbotcfg.steps import Regen, Configure, Make, MakeDocs, MakeManPages, Test


class GerritCheckoutFactory(util.BuildFactory):
    """Base class build factory.

    This build factory adds the common steps to checkout source from the gerrit
    git repo.
    """

    gerrit_lock = util.MasterLock("gerrit")
    gerrit_lock_count = 1  # Max number of concurrent checkouts.

    def __init__(self, repo=None, start_delay=0, workdir='build', **kwargs):
        """Checkout source code from the Gerrit repository.

        Checkout the source using a lock to prevent too much load on the
        Gerrit server.

        Args:
            repo:        The Gerrit git repo URL.
            start_delay: The number of seconds to delay before checkout.
                         This delay allows the gerrit server
            workdir:     The directory to checkout source files.
        """
        super().__init__(**kwargs)
        if not repo:
            repo = 'git://git.openafs.org/openafs.git'

        if start_delay:
            self.addStep(steps.ShellCommand(name='delay',
                                            command=self.delay(start_delay)))

        self.addStep(steps.Gerrit(
            workdir=workdir,
            repourl=repo,
            mode='full',
            method='fresh',
            retryFetch=True,
            timeout=3600,
            locks=[self.gerrit_lock.access('counting',
                                           self.gerrit_lock_count)]))

        self.addStep(steps.ShellCommand(
            name='git show',
            workdir=workdir,
            command=['git', 'log', '-n', '1', '--stat']))

        self.addStep(steps.ShellCommand(
            name='git gc',
            workdir=workdir,
            command=['git', 'gc', '--auto']))

    def delay(self, seconds):
        return ['sleep', seconds]


class UnixBuildFactory(GerritCheckoutFactory):
    """Build with autoconf and make.

    Build OpenAFS on Unix-like systems with autoconf and make. Optionally
    render the documentation and run the TAB unit tests.
    """

    DOCS = ('AdminGuide', 'AdminRef', 'QuickStartUnix', 'UserGuide')

    def __init__(self,
                 objdir=False,
                 configure=None,
                 make='make',
                 pretty=False,
                 jobs=4,
                 target='all',
                 docs=False,
                 test=False,
                 **kwargs):
        """Create a UnixBuildFactory instance.

        Args:
            objdir:       Build in separate directory when true (boolean)
            configure:    configure options (string)
            make:         make command (string)
            pretty:       Pretty make output (boolean)
            jobs:         Number of make jobs (int)
            target:       The top level makefile target (string)
            docs:         Also render the docs when true (boolean)
            test:         Also run the TAP unit tests when true (boolean)
        """
        # Use separate source and build directories in objdir mode.
        if objdir:
            checkoutdir = 'source'
            builddir = 'build'
            cf = '../source/configure'
        else:
            checkoutdir = 'build'
            builddir = 'build'
            cf = './configure'

        super().__init__(workdir=checkoutdir, **kwargs)

        if builddir != checkoutdir:
            self.addStep(steps.RemoveDirectory(dir=builddir))
            self.addStep(steps.MakeDirectory(dir=builddir))

        self.addStep(Regen(workdir=checkoutdir,
                           manpages=target.startswith('dest')))

        self.addStep(Configure(configure=cf, options=configure))

        self.addStep(Make(make=make, jobs=jobs,
                          pretty=pretty, target=target))

        if docs:
            self.addStep(MakeDocs(self.DOCS, make=make))

        if docs or test:
            self.addStep(MakeManPages())

        if test:
            self.addStep(Test(make=make))


class WindowsBuildFactory(GerritCheckoutFactory):
    """Build on Windows with a script.

    The 'build-openafs.cmd' script must be manually installed on the
    Windows buildbot worker.
    """
    def __init__(self, arch='amd64', variant='free', **kwargs):
        super().__init__(**kwargs)
        self.addStep(steps.ShellCommand(
            name='build-openafs',
            command=['build-openafs.cmd', arch, variant]))

    def delay(self, seconds):
        """Delay with ping.

        Overrides the base class delay method to run 'ping' instead of
        'sleep', since the 'sleep' command is not available on Windows.
        """
        return ['ping', '-n', seconds, 'localhost']


class ELRpmBuildFactory(GerritCheckoutFactory):
    """Build OpenAFS RPM packages on a RHEL-like system.

    Build the RPM packages on a RHEL-like system from a git checkout.  After
    the packages are built, unpack the OpenAFS DKMS package and build the
    OpenAFS kernel module to verify the DKMS package is usable.

    This build factory downloads and runs several scripts to build the RPM
    packages. The scripts are downloaded from the build-tools directory on the
    buildbot master.  The in-tree `make-srpm.pl` script is avoided by the build
    factory since it is far too fragile.

    Scripts:
        make-rpm-workspace.sh   Create and populate the rpmbuild/SOURCES.
        unpack-dkms-rpm.sh      Unpack the DKMS package.

    Args:
        build_dkms_source
    """

    def __init__(self, build_dkms_source=False, **kwargs):
        super().__init__(**kwargs)

        self.addStep(steps.MakeDirectory(dir='build/packages'))

        self.addStep(steps.ShellCommand(
            name='Create source distribution tarballs',
            command=['build-tools/make-release', '--dir=packages', 'HEAD']))

        self.addStep(steps.FileDownload(
            name='Download make-rpm-workspace script',
            mastersrc='build-scripts/make-rpm-workspace.sh',
            workerdest='packages/make-rpm-workspace.sh',
            mode=0o755))

        self.addStep(steps.ShellCommand(
            name='Create rpmbuild directory',
            command=['packages/make-rpm-workspace.sh']))

        self.addStep(steps.RpmBuild(
            specfile='packages/rpmbuild/SPECS/openafs.spec',
            topdir='`pwd`/packages/rpmbuild',
            builddir='`pwd`/packages/rpmbuild/BUILD',
            rpmdir='`pwd`/packages/rpmbuild/RPMS',
            sourcedir='`pwd`/packages/rpmbuild/SOURCES',
            srcrpmdir='`pwd`/packages/rpmbuild/SRPMS'))

        if build_dkms_source:
            self.addStep(steps.FileDownload(
                name='Download unpack-dkms-rpm script',
                mastersrc='build-scripts/unpack-dkms-rpm.sh',
                workerdest='packages/unpack-dkms-rpm.sh',
                mode=0o755))

            self.addStep(steps.ShellCommand(
                name='Unpack dkms-openafs rpm',
                command=['packages/unpack-dkms-rpm.sh']))

            self.addStep(steps.Configure(
                command=['./configure', '--with-linux-kernel-packaging'],
                workdir='build/packages/dkms/usr/src/openafs',
                logfiles={'config.log': 'config.log'}))

            self.addStep(steps.Compile(
                command=['make', '-j', '4', 'V=0'],
                workdir='build/packages/dkms/usr/src/openafs'))
