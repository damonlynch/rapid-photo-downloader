# SPDX-FileCopyrightText: Copyright 2010-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Notify user of problems when downloading: problems with subfolder and filename
generation, download errors, and so forth

Goals
=====

Group problems into tasks:
  1. scanning
  2. copying
  3. renaming (presented to user as finalizing file and download subfolder names)
  4. backing up - per backup device

Present messages in a human-readable manner.
Multiple metadata problems can occur: group them.
Distinguish error severity

"""

import logging
from collections import deque
from collections.abc import Iterator
from html import escape

from raphodo.camera import gphoto2_named_error
from raphodo.constants import ErrorType
from raphodo.internationalisation.utilities import make_internationalized_list


def make_href(name: str, uri: str) -> str:
    """
    Construct a hyperlink.
    """

    # Note: keep consistent with ErrorReport._saveUrls()
    return f'<a href="{uri}">{escape(name)}</a>'


class Problem:
    def __init__(
        self,
        name: str | None = None,
        uri: str | None = None,
        exception: Exception | None = None,
        **attrs,
    ) -> None:
        for attr, value in attrs.items():
            setattr(self, attr, value)
        self.name = name
        self.uri = uri
        self.exception = exception

    @property
    def title(self) -> str:
        logging.critical(
            "title() not implemented in subclass %s", self.__class__.__name__
        )
        return "undefined"

    @property
    def body(self) -> str:
        logging.critical(
            "body() not implemented in subclass %s", self.__class__.__name__
        )
        return "undefined"

    @property
    def details(self) -> list[str]:
        if self.exception is not None:
            try:
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                return [
                    escape(_("Error: %(errno)s %(strerror)s"))
                    % dict(errno=self.exception.errno, strerror=self.exception.strerror)
                ]
            except AttributeError:
                return [escape(_("Error: %s")) % self.exception]
        else:
            return []

    @property
    def href(self) -> str:
        if self.name and self.uri:
            return make_href(name=self.name, uri=self.uri)
        else:
            logging.critical(
                "href() is missing name or uri in subclass %s", self.__class__.__name__
            )

    @property
    def severity(self) -> ErrorType:
        return ErrorType.warning


class SeriousProblem(Problem):
    @property
    def severity(self) -> ErrorType:
        return ErrorType.serious_error


class CameraGpProblem(SeriousProblem):
    @property
    def details(self) -> list[str]:
        try:
            return [
                escape(_("GPhoto2 Error: %s"))
                % escape(gphoto2_named_error(self.gp_code))
            ]
        except AttributeError:
            return []


class CameraInitializationProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(
            _(
                "Unable to initialize the camera, probably because another program is "
                "using it. No files were copied from it."
            )
        )

    @property
    def severity(self) -> ErrorType:
        return ErrorType.critical_error


class CameraDirectoryReadProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to read directory %s")) % self.href


class CameraFileInfoProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return (
            escape(_("Unable to access modification time or size from %s")) % self.href
        )


class CameraFileReadProblem(CameraGpProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to read file %s")) % self.href


class FileWriteProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to write file %s")) % self.href


class FileMoveProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to move file %s")) % self.href


class FileDeleteProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to remove file %s")) % self.href


class FileCopyProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to copy file %s")) % self.href


class FileZeroLengthProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_("Zero length file %s will not be downloaded")) % self.href


class FsMetadataReadProblem(Problem):
    @property
    def body(self) -> str:
        return (
            escape(_("Could not determine filesystem modification time for %s"))
            % self.href
        )


class FileMetadataLoadProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_("Unable to load metadata from %s")) % self.href


class FileMetadataLoadProblemNoDownload(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            _(
                "Unable to load metadata from %(name)s. The %(filetype)s was not "
                "downloaded."
            )
        ) % dict(filetype=self.file_type, name=self.href)


class FsMetadataWriteProblem(Problem):
    @property
    def body(self) -> str:
        return (
            escape(
                _(
                    "An error occurred setting a file's filesystem metadata on the "
                    "filesystem %s. "
                    "If this error occurs again on the same filesystem, it will not be "
                    "reported again."
                )
            )
            % self.href
        )

    @property
    def details(self) -> list[str]:
        return [
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            escape(_("Error: %(errno)s %(strerror)s"))
            % dict(errno=e.errno, strerror=e.strerror)
            for e in self.mdata_exceptions
        ]


class UnhandledFileProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return (
            escape(_("Encountered unhandled file %s. It will not be downloaded."))
            % self.href
        )


class FileAlreadyExistsProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            _("%(filetype)s %(destination)s already exists.")
        ) % dict(filetype=escape(self.file_type_capitalized), destination=self.href)

    @property
    def details(self) -> list[str]:
        d = list()
        d.append(
            escape(
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _(
                    "The existing %(filetype)s %(destination)s was last modified on "
                    "%(date)s at %(time)s."
                )
            )
            % dict(
                filetype=escape(self.file_type),
                date=escape(self.date),
                time=escape(self.time),
                destination=self.href,
            )
        )
        d.append(
            escape(
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _("The %(filetype)s %(source)s was not downloaded from %(device)s.")
            )
            % dict(
                filetype=escape(self.file_type), source=self.source, device=self.device
            )
        )
        return d


class IdentifierAddedProblem(FileAlreadyExistsProblem):
    @property
    def details(self) -> list[str]:
        d = list()
        d.append(
            escape(
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _(
                    "The existing %(filetype)s %(destination)s was last modified on "
                    "%(date)s at %(time)s."
                )
            )
            % dict(
                filetype=escape(self.file_type),
                date=escape(self.date),
                time=escape(self.time),
                destination=self.href,
            )
        )
        d.append(
            escape(
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _("The %(filetype)s %(source)s was downloaded from %(device)s.")
            )
            % dict(
                filetype=escape(self.file_type), source=self.source, device=self.device
            )
        )
        d.append(
            escape(_("The unique identifier '%s' was added to the filename."))
            % self.identifier
        )
        return d

    @property
    def severity(self) -> ErrorType:
        return ErrorType.warning


class BackupAlreadyExistsProblem(FileAlreadyExistsProblem):
    @property
    def details(self) -> list[str]:
        d = list()
        d.append(
            escape(
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _(
                    "The existing backup %(filetype)s %(destination)s was last "
                    "modified on %(date)s at %(time)s."
                )
            )
            % dict(
                filetype=escape(self.file_type),
                date=escape(self.date),
                time=escape(self.time),
                destination=self.href,
            )
        )
        d.append(
            escape(
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _("The %(filetype)s %(source)s was not backed up from %(device)s.")
            )
            % dict(
                filetype=escape(self.file_type), source=self.source, device=self.device
            )
        )
        return d


class BackupOverwrittenProblem(BackupAlreadyExistsProblem):
    @property
    def details(self) -> list[str]:
        d = list()
        d.append(
            escape(
                # Translators: %(variable)s represents Python code, not a plural of the
                # term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _(
                    "The previous backup %(filetype)s %(destination)s was last "
                    "modified on %(date)s at %(time)s."
                )
            )
            % dict(
                filetype=escape(self.file_type),
                date=escape(self.date),
                time=escape(self.time),
                destination=self.name,
            )
        )
        d.append(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            escape(
                _(
                    "The %(filetype)s %(source)s from %(device)s was backed up, "
                    "overwriting the previous backup %(filetype)s."
                )
            )
            % dict(
                filetype=escape(self.file_type), source=self.source, device=self.device
            )
        )
        return d

    @property
    def severity(self) -> ErrorType:
        return ErrorType.warning


class DuplicateFileWhenSyncingProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            _(
                "When synchronizing RAW + JPEG sequence values, a duplicate "
                "%(filetype)s %(file)s was encountered, and was not downloaded."
            )
        ) % dict(file=self.href, filetype=self.file_type)


class SameNameDifferentExif(Problem):
    @property
    def body(self) -> str:
        return escape(
            _(
                "When synchronizing RAW + JPEG sequence values, photos were detected "
                "with the same filenames, but taken at different times:"
            )
        )

    @property
    def details(self) -> list[str]:
        return [
            escape(
                # Translators: %(variable)s represents Python code, not a plural of
                # the term variable. You must keep the %(variable)s untranslated, or the
                # program will crash.
                _(
                    "%(image1)s was taken on %(image1_date)s at %(image1_time)s, "
                    "and %(image2)s on %(image2_date)s at %(image2_time)s."
                )
            )
            % dict(
                image1=self.image1,
                image1_date=self.image1_date,
                image1_time=self.image1_time,
                image2=self.image2,
                image2_date=self.image2_date,
                image2_time=self.image2_time,
            )
        ]


class RenamingAssociateFileProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to finalize the filename for %s")) % self.source


class FilenameNotFullyGeneratedProblem(Problem):
    def __init__(
        self,
        name: str | None = None,
        uri: str | None = None,
        exception: Exception | None = None,
        **attrs,
    ) -> None:
        super().__init__(name=name, uri=uri, exception=exception, **attrs)
        self.missing_metadata = []
        self.file_type = ""
        self.destination = ""
        self.source = ""
        self.bad_converstion_date_time = False
        self.bad_conversion_exception: Exception | None = None
        self.invalid_date_time = False
        self.missing_extension = False
        self.missing_image_no = False
        self.component_error = False
        self.component_problem = ""
        self.component_exception = None

    def has_error(self) -> bool:
        """
        :return: True if any of the errors occurred
        """

        return (
            bool(self.missing_metadata)
            or self.invalid_date_time
            or self.bad_converstion_date_time
            or self.missing_extension
            or self.missing_image_no
            or self.component_error
        )

    @property
    def body(self) -> str:
        return escape(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            _(
                "The filename %(destination)s was not fully generated for "
                "%(filetype)s %(source)s."
            )
        ) % dict(
            destination=self.destination, filetype=self.file_type, source=self.source
        )

    @property
    def details(self) -> list[str]:
        d = []
        if len(self.missing_metadata) == 1:
            d.append(
                escape(
                    # Translators: %(variable)s represents Python code, not a plural of
                    # the term variable. You must keep the %(variable)s untranslated, or
                    # the program will crash.
                    _("The %(type)s metadata is missing.")
                )
                % dict(type=self.missing_metadata[0])
            )
        elif len(self.missing_metadata) > 1:
            d.append(
                escape(_("The following metadata is missing: %s."))
                % make_internationalized_list(self.missing_metadata)
            )

        if self.bad_converstion_date_time:
            d.append(
                escape(_("Date/time conversion failed: %s."))
                % self.bad_conversion_exception
            )

        if self.invalid_date_time:
            d.append(
                escape(
                    _(
                        "Could not extract valid date/time metadata or determine the "
                        "file modification time."
                    )
                )
            )

        if self.missing_extension:
            d.append(escape(_("Filename does not have an extension.")))

        if self.missing_image_no:
            d.append(escape(_("Filename does not have a number component.")))

        if self.component_error:
            d.append(
                escape(_("Error generating component %(component)s. Error: %(error)s"))
                % dict(component=self.component_problem, error=self.component_exception)
            )

        return d


class FolderNotFullyGeneratedProblemProblem(FilenameNotFullyGeneratedProblem):
    @property
    def body(self) -> str:
        return escape(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            _(
                "The download subfolders %(folder)s were only partially generated for "
                "%(filetype)s %(source)s."
            )
        ) % dict(folder=self.destination, filetype=self.file_type, source=self.source)


class NoDataToNameProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            _(
                "There is no data with which to generate the %(subfolder_file)s for "
                "%(filename)s. The %(filetype)s was not downloaded."
            )
        ) % dict(
            subfolder_file=self.area,
            filename=self.href,
            filetype=self.file_type,
        )


class RenamingFileProblem(SeriousProblem):
    @property
    def body(self) -> str:
        return escape(
            # Translators: %(variable)s represents Python code, not a plural of the term
            # variable. You must keep the %(variable)s untranslated, or the program will
            # crash.
            _(
                "Unable to create the %(filetype)s %(destination)s in %(folder)s. The "
                "download file was %(source)s in %(device)s. It was not downloaded."
            )
        ) % dict(
            filetype=escape(self.file_type),
            destination=escape(self.destination),
            folder=self.folder,
            source=self.href,
            device=self.device,
        )


class SubfolderCreationProblem(Problem):
    @property
    def body(self) -> str:
        return escape(_("Unable to create the download subfolder %s.")) % self.folder

    @property
    def severity(self) -> ErrorType:
        return ErrorType.critical_error


class BackupSubfolderCreationProblem(SubfolderCreationProblem):
    @property
    def body(self) -> str:
        return escape(_("Unable to create the backup subfolder %s.")) % self.folder


class Problems:
    def __init__(
        self,
        name: str | None = "",
        uri: str | None = "",
        problem: Problem | None = None,
    ) -> None:
        self.problems = deque()
        self.name = name
        self.uri = uri
        if problem:
            self.append(problem=problem)

    def __len__(self) -> int:
        return len(self.problems)

    def __iter__(self) -> Iterator[Problem]:
        return iter(self.problems)

    def __getitem__(self, index: int) -> Problem:
        return self.problems[index]

    def append(self, problem: Problem) -> None:
        self.problems.append(problem)

    @property
    def title(self) -> str:
        logging.critical(
            "title() not implemented in subclass %s", self.__class__.__name__
        )
        return "undefined"

    @property
    def body(self) -> str:
        return "body"

    @property
    def details(self) -> list[str]:
        return []

    @property
    def href(self) -> str:
        if self.name and self.uri:
            return make_href(name=self.name, uri=self.uri)
        else:
            logging.critical(
                "href() is missing name or uri in %s", self.__class__.__name__
            )


class ScanProblems(Problems):
    @property
    def title(self) -> str:
        return escape(_("Problems scanning %s")) % self.href


class CopyingProblems(Problems):
    @property
    def title(self) -> str:
        return escape(_("Problems copying from %s")) % self.href


class RenamingProblems(Problems):
    @property
    def title(self) -> str:
        return escape(
            _("Problems while finalizing filenames and generating subfolders")
        )


class BackingUpProblems(Problems):
    @property
    def title(self) -> str:
        return escape(_("Problems backing up to %s")) % self.href
