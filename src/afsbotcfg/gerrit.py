# Copyright (c) 2019 Sine Nomine Associates
#
# This file copies/extends portions of Buildbot forcescheduler.
# This software is available at no charge under the terms
# of the GNU General Public License version 2 (GPLv2) as
# available from the OSI(Open Software Initiative) website.

# THE SOFTWARE IS PROVIDED 'AS IS' AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.


from buildbot.plugins import util


def summaryCB(buildInfoList, results, status, arg):

    def report_build_status(buildlist, finalstatus=None):
        for info in buildlist:
            msg = "    Builder %(name)s %(resultText)s (%(text)s)" % info
            link = info.get('url', None)
            if link:
                msg += " - " + link
            if finalstatus:
                msg += "\n       Final build status %(resultText)s" % finalstatus[info['name']]
            msg += "."
            yield msg

    msgs = list(arg)   # summaryArg contains the message headers.

    # sort buildinfo by builder and completed build time
    # we want to get the final result of any particular builder
    # in case there was a retry that ended up with a successful build
    buildInfoList.sort(
        key=lambda buildinfo: (buildinfo['name'], buildinfo['build']['complete_at']))

    builderFinalStatus = dict()
    for buildInfo in buildInfoList:
        builderFinalStatus[buildInfo['name']] = buildInfo

    # Possible results: SUCCESS WARNINGS FAILURE SKIPPED EXCEPTION RETRY CANCELLED
    successfulBuilds = [
        fstatus for fstatus in builderFinalStatus.values() if fstatus['result'] == util.SUCCESS
    ]
    failedBuilds = [
        fstatus for fstatus in builderFinalStatus.values() if fstatus['result'] != util.SUCCESS
    ]

    # typically retries or interrupted builds
    restartedBuilds = [
        buildinfo for buildinfo in buildInfoList if buildinfo not in successfulBuilds and buildinfo not in failedBuilds
    ]

    msgs.append("Final Build Status (failed %d succeeded %d):" %
                (len(failedBuilds), len(successfulBuilds)))

    if len(failedBuilds) > 0:
        msgs.append("\n Failed Builds:")
        msgs.extend(report_build_status(failedBuilds))

    if len(successfulBuilds) > 0:
        msgs.append("\n Successful Builds:")
        msgs.extend(report_build_status(successfulBuilds))

    if len(restartedBuilds) > 0:
        msgs.append("\n Restarted Builds:")
        msgs.extend(report_build_status(restartedBuilds, finalstatus=builderFinalStatus))

    message = '\n\n'.join(msgs)

    if len(successfulBuilds) != 0 and len(failedBuilds) == 0:
        verified = 1
    else:
        verified = 0

    return dict(message=message, labels={'Verified': verified})