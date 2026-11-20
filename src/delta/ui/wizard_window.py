"""The setup wizard window: walks WizardModel's steps and creates the repository."""

import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from delta.i18n import _
from delta.ui.client import DeltaClient
from delta.ui.disk import inspect_path
from delta.ui.wizard import SetupRequest, Step, WizardModel, repository_exists
from delta.ui.wizard_destination import DestinationPage
from delta.ui.wizard_pages import FoldersPage, RecoveryPage, SummaryPage


class SetupWizard(Adw.Window):
    def __init__(
        self, parent, client: DeltaClient, settings, on_done: Callable[[], None], change: bool = False
    ) -> None:
        super().__init__(
            transient_for=parent, modal=True,
            title=_("Change where backups are kept") if change else _("Set up backups"),
            default_width=560, default_height=640,
        )
        self._client, self._settings, self._on_done = client, settings, on_done
        self._change = change
        self._model = WizardModel(
            home=os.path.expanduser("~"), inspect=inspect_path, keep_folders=change,
            current=settings.get_string("repository-location") if change and settings is not None else "",
        )
        self._touched: set[Step] = set()
        self._busy = False
        self._adopting = False
        self._request: SetupRequest | None = None
        self._job: str | None = None
        self._finished: dict[str, tuple[bool, str]] = {}  # a result can beat the call's reply

        self._pages = {
            Step.DESTINATION: DestinationPage(self._model, self, self._on_change),
            Step.FOLDERS: FoldersPage(self._model, self, self._on_change),
            Step.RECOVERY: RecoveryPage(self._model, self, self._on_change),
            Step.SUMMARY: SummaryPage(self._model, self, self._on_change),
        }
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vexpand=True)
        for step, page in self._pages.items():
            self._stack.add_named(page, step.value)

        header = Adw.HeaderBar()
        self._back = Gtk.Button(label=_("Back"))
        self._back.connect("clicked", self._on_back)
        header.pack_start(self._back)
        self._next = Gtk.Button()
        self._next.add_css_class("suggested-action")
        self._next.connect("clicked", self._on_next)
        header.pack_end(self._next)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self._stack)
        self.set_content(toolbar)

        self._subscription = client.on_backup_finished(self._on_finished)
        self.connect("close-request", self._on_close)
        self._show()

    # -- navigation ---------------------------------------------------------------

    def _show(self) -> None:
        if self._model.step is Step.SUMMARY:
            self._pages[Step.SUMMARY].refresh()
            if self._model.reuses_repository:
                self._request = self._model.request()
                self._pages[Step.SUMMARY].offer_existing(self._use_existing)
            else:
                self._pages[Step.SUMMARY].hide_existing()
        self._stack.set_visible_child_name(self._model.step.value)
        self._sync()

    def _sync(self) -> None:
        step = self._model.step
        problems = self._model.errors() if step in self._touched else []
        self._pages[step].show_problems(problems)
        self._back.set_sensitive(step is not self._model.steps[0] and not self._busy)
        self._next.set_sensitive(self._model.can_continue() and not self._busy)
        self._next.set_visible(not (self._model.is_last and self._model.reuses_repository))  # it has its own button
        last = _("Use this destination") if self._change else _("Create backups")
        self._next.set_label(last if self._model.is_last else _("Next"))

    def _on_change(self) -> None:
        self._touched.add(self._model.step)
        self._sync()

    def _on_back(self, button) -> None:
        if self._model.back():
            self._show()

    def _on_next(self, button) -> None:
        self._touched.add(self._model.step)
        if self._model.is_last:
            self._create()
        elif self._model.next():
            self._show()
        else:
            self._sync()

    # -- creating the repository ----------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._pages[Step.SUMMARY].set_busy(busy)
        self._sync()

    def _create(self) -> None:
        request = self._model.request()
        self._request = request
        self._adopting = False
        self._set_busy(True)
        self._client.create_repository(request.location, request.passphrase, self._on_started)

    def _use_existing(self, passphrase: str) -> None:
        if self._request is None:
            return
        self._adopting = True
        self._pages[Step.SUMMARY].show_problems([])
        self._set_busy(True)
        self._client.use_repository(self._request.location, passphrase, self._on_started)

    def _on_started(self, job_id, error) -> None:
        if error:
            self._fail(error)
            return
        self._job = job_id
        if job_id in self._finished:
            self._conclude(*self._finished.pop(job_id))

    def _on_finished(self, job_id: str, ok: bool, message: str) -> None:
        if self._job is None:
            self._finished[job_id] = (ok, message)
        elif job_id == self._job:
            self._conclude(ok, message)

    def _conclude(self, ok: bool, message: str) -> None:
        if not ok:
            self._fail(message)
            return
        if self._settings is not None and self._request is not None and not self._change:
            self._settings.set_strv("backup-sources", list(self._request.folders))
        self._model.own_passphrase = self._model.own_confirmation = ""
        self._on_done()
        self.close()

    def _fail(self, message: str) -> None:
        self._job = None
        self._set_busy(False)
        summary = self._pages[Step.SUMMARY]
        summary.show_problems([message])
        if repository_exists(message) or self._adopting:
            summary.offer_existing(self._use_existing)  # a wrong passphrase must be retryable
        else:
            summary.hide_existing()

    def _on_close(self, window) -> bool:
        self._client.unsubscribe(self._subscription)
        return False
