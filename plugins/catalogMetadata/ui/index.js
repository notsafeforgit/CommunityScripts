function register(host) {
  if (host.version !== "1" || !host.react || !host.forms || !host.operations) {
    throw new Error(
      "Catalog review requires the current Stash v3 plugin UI host. Update Stash first."
    );
  }
  const React = host.react;
  const { useState, useEffect, useCallback, useRef } = React;
  const { useForm, z } = host.forms;
  const {
    Alert,
    AlertTitle,
    AlertDescription,
    Badge,
    Button,
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    CardFooter,
    Combobox,
    ComboboxInput,
    ComboboxContent,
    ComboboxEmpty,
    ComboboxList,
    ComboboxItem,
    Field,
    FieldGroup,
    FieldLabel,
    FieldDescription,
    FieldError,
    Input,
    Select,
    SelectTrigger,
    SelectValue,
    SelectContent,
    SelectGroup,
    SelectItem,
    Spinner
  } = host.ui;
  const { Link } = host.router;
  const msg = (id, defaultMessage, values) => host.intl.formatMessage({ id: `catalogMetadata.review.${id}`, defaultMessage }, values);
  const personLabel = (p) => `${p.name}${p.disambiguation ? ` (${p.disambiguation})` : ""} \xB7 #${p.id}`;
  const errorMessage = (error) => error instanceof Error ? error.message : String(error);
  const statusLabel = (status) => ({
    attention: msg("attention", "Needs review"),
    conflict: msg("conflict", "Conflicting links"),
    candidate: msg("candidate", "Name or alias match"),
    proposed: msg("proposed", "Ready to review"),
    linked: msg("linked", "Linked"),
    unmatched: msg("unmatched", "No match"),
    all: msg("all", "All catalogs")
  })[status];
  function Account({ account, performers }) {
    return /* @__PURE__ */ React.createElement("div", { className: "catalog-review-account" }, /* @__PURE__ */ React.createElement("div", { className: "catalog-review-line" }, /* @__PURE__ */ React.createElement(Badge, { variant: "secondary" }, account.platform), /* @__PURE__ */ React.createElement("strong", null, account.handles.join(", ") || account.source_id)), /* @__PURE__ */ React.createElement("code", null, account.account_key), account.evidence?.length > 0 && /* @__PURE__ */ React.createElement("ul", { className: "catalog-review-evidence" }, account.evidence.map((item, index) => {
      const p = performers.find((person) => person.id === item.performer_id);
      const kind = {
        explicit_link: msg("explicit", "Explicit account link"),
        saved_link: msg("saved", "Saved catalog link"),
        profile_url: msg("profile", "Performer profile URL"),
        name_only: msg("name_only", "Name or alias only; review required")
      }[item.kind];
      return /* @__PURE__ */ React.createElement("li", { key: `${item.kind}:${item.performer_id}:${index}` }, /* @__PURE__ */ React.createElement("span", null, kind, ": ", p ? personLabel(p) : `#${item.performer_id}`), item.url && /* @__PURE__ */ React.createElement("a", { href: item.url, target: "_blank", rel: "noreferrer" }, item.url), item.ambiguous && /* @__PURE__ */ React.createElement("span", null, msg("reused", "This handle appears on multiple account IDs.")));
    })));
  }
  function ReviewPanel({ row, performers, onClose, onApplied, onBusy }) {
    const initial = row.status === "conflict" ? null : performers.find((p) => p.id === row.performer_id) ?? null;
    const [search, setSearch] = useState("");
    const [preview, setPreview] = useState(null);
    const [pending, setPending] = useState(null);
    const [error, setError] = useState(null);
    const alive = useRef(true);
    const panel = useRef(null);
    useEffect(() => {
      alive.current = true;
      panel.current?.focus();
      return () => {
        alive.current = false;
      };
    }, []);
    const form = useForm({
      defaultValues: { performer: initial },
      validators: {
        onChange: z.object({
          performer: z.object({ id: z.string().min(1) }).nullable().refine(Boolean, msg("choose", "Choose a performer."))
        })
      },
      onSubmit: async ({ value }) => {
        if (!value.performer) return;
        setPending("preview");
        onBusy(true);
        setError(null);
        setPreview(null);
        try {
          const next = await host.operations.query("review_link", {
            catalog_id: row.catalog_id,
            performer_id: value.performer.id
          });
          if (alive.current) setPreview(next);
        } catch (error2) {
          if (alive.current) setError(errorMessage(error2));
        } finally {
          if (alive.current) {
            setPending(null);
            onBusy(false);
          }
        }
      }
    });
    async function apply() {
      if (!preview || pending || preview.blocked_reason) return;
      setPending("apply");
      onBusy(true);
      setError(null);
      try {
        const result = await host.operations.mutate("apply_link", {
          catalog_id: row.catalog_id,
          performer_id: preview.performer.id,
          review_token: preview.review_token
        });
        if (alive.current) onApplied(result);
      } catch (error2) {
        if (alive.current) {
          setError(errorMessage(error2));
          setPreview(null);
        }
      } finally {
        if (alive.current) setPending(null);
        onBusy(false);
      }
    }
    const needle = search.trim().toLocaleLowerCase();
    const options = [...performers].sort(
      (a, b) => Number(row.candidate_ids.includes(b.id)) - Number(row.candidate_ids.includes(a.id))
    ).filter(
      (p) => !needle || [p.id, p.name, p.disambiguation, ...p.alias_list, ...p.urls].some(
        (value) => value?.toLocaleLowerCase().includes(needle)
      )
    ).slice(0, 40);
    return /* @__PURE__ */ React.createElement(
      Card,
      {
        className: "catalog-review-detail",
        ref: panel,
        tabIndex: -1,
        "aria-labelledby": "catalog-review-title"
      },
      /* @__PURE__ */ React.createElement(CardHeader, null, /* @__PURE__ */ React.createElement(CardTitle, { id: "catalog-review-title" }, msg("review_catalog", "Review {label}", { label: row.label })), /* @__PURE__ */ React.createElement(CardDescription, null, msg(
        "whole_catalog",
        "Choose the performer who owns every account below. Accounts already joined in one creator catalog stay together."
      ))),
      /* @__PURE__ */ React.createElement(CardContent, { className: "catalog-review-stack" }, /* @__PURE__ */ React.createElement("code", null, row.catalog_id), row.conflicts.map((conflict, i) => /* @__PURE__ */ React.createElement(Alert, { key: i, variant: "destructive" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("conflict", "Conflicting links")), /* @__PURE__ */ React.createElement(AlertDescription, null, conflict.reason))), row.accounts.map((account) => /* @__PURE__ */ React.createElement(Account, { key: account.account_key, account, performers })), /* @__PURE__ */ React.createElement(
        "form",
        {
          onSubmit: (event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }
        },
        /* @__PURE__ */ React.createElement(FieldGroup, null, /* @__PURE__ */ React.createElement(form.Field, { name: "performer" }, (field) => {
          const invalid = field.state.meta.isTouched && !field.state.meta.isValid;
          return /* @__PURE__ */ React.createElement(Field, { "data-invalid": invalid }, /* @__PURE__ */ React.createElement(FieldLabel, { htmlFor: "catalog-review-performer" }, msg("performer", "Stash performer")), /* @__PURE__ */ React.createElement(
            Combobox,
            {
              items: options,
              filter: null,
              value: field.state.value,
              disabled: !!pending,
              onValueChange: (value) => {
                field.handleChange(value);
                setPreview(null);
                setError(null);
              },
              itemToStringLabel: personLabel,
              itemToStringValue: (p) => p.id,
              isItemEqualToValue: (a, b) => a.id === b.id,
              onOpenChange: (open) => {
                if (open) setSearch("");
              },
              onInputValueChange: (value, details) => {
                if (["input-change", "input-clear"].includes(details.reason))
                  setSearch(value);
              }
            },
            /* @__PURE__ */ React.createElement(
              ComboboxInput,
              {
                id: "catalog-review-performer",
                showClear: true,
                onBlur: field.handleBlur,
                "aria-invalid": invalid,
                placeholder: msg(
                  "search_performers",
                  "Search names, aliases, profile URLs or IDs"
                )
              }
            ),
            /* @__PURE__ */ React.createElement(ComboboxContent, null, /* @__PURE__ */ React.createElement(ComboboxEmpty, null, msg("no_performers", "No matching performers")), /* @__PURE__ */ React.createElement(ComboboxList, null, (p) => /* @__PURE__ */ React.createElement(ComboboxItem, { key: p.id, value: p }, /* @__PURE__ */ React.createElement("div", { className: "catalog-review-option" }, /* @__PURE__ */ React.createElement("strong", null, personLabel(p)), p.alias_list.length > 0 && /* @__PURE__ */ React.createElement("span", null, msg("aliases", "Aliases: {names}", {
              names: p.alias_list.join(", ")
            }))))))
          ), /* @__PURE__ */ React.createElement(FieldDescription, null, msg(
            "suggested_first",
            "Candidates appear first. Names and aliases can collide; check the performer ID, disambiguation and profile evidence."
          )), invalid && /* @__PURE__ */ React.createElement(FieldError, { errors: field.state.meta.errors }));
        }), /* @__PURE__ */ React.createElement(Button, { type: "submit", variant: "outline", disabled: !!pending }, pending === "preview" && /* @__PURE__ */ React.createElement(Spinner, null), msg("preview", "Preview link")))
      ), error && /* @__PURE__ */ React.createElement(Alert, { variant: "destructive", role: "alert" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("failed", "Could not complete the request")), /* @__PURE__ */ React.createElement(AlertDescription, null, error, /* @__PURE__ */ React.createElement("p", null, msg(
        "retry_preview",
        "Preview again to retry with current data. A failed apply may have saved the explicit choice; catalog copies can be retried."
      )))), preview && /* @__PURE__ */ React.createElement(
        "section",
        {
          "aria-label": msg("proposed_changes", "Proposed changes"),
          className: "catalog-review-stack"
        },
        /* @__PURE__ */ React.createElement("h3", null, msg("link_to", "Link to {performer}", {
          performer: personLabel(preview.performer)
        })),
        /* @__PURE__ */ React.createElement("p", null, msg(
          "preview_explanation",
          "Save the selected accounts as explicit links. All catalogs below will share this performer identity and use the performer\u2019s name as their label."
        )),
        preview.catalogs.map((catalog) => /* @__PURE__ */ React.createElement("div", { className: "catalog-review-preview-catalog", key: catalog.id }, /* @__PURE__ */ React.createElement("div", { className: "catalog-review-line" }, /* @__PURE__ */ React.createElement("strong", null, catalog.label), /* @__PURE__ */ React.createElement(Badge, { variant: "outline" }, catalog.id === preview.target_catalog ? msg("destination", "Destination") : msg("merge_into", "Merge into destination"))), /* @__PURE__ */ React.createElement("code", null, catalog.id), /* @__PURE__ */ React.createElement("ul", null, catalog.accounts.map((account) => /* @__PURE__ */ React.createElement("li", { key: account.account_key }, account.platform, ": ", account.handles.join(", "), " ", /* @__PURE__ */ React.createElement("code", null, account.account_key)))))),
        /* @__PURE__ */ React.createElement("p", null, msg(
          "preserved",
          "Source account IDs, posts and captured evidence are preserved. Media files stay in place. This does not merge Stash performers or re-import existing scenes and images."
        )),
        preview.other_conflicts.length > 0 && /* @__PURE__ */ React.createElement(Alert, null, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("other_conflicts", "Other conflicts remain")), /* @__PURE__ */ React.createElement(AlertDescription, null, msg(
          "other_conflicts_detail",
          "Only the catalogs shown above will be linked. Other conflicting catalogs remain for review."
        ))),
        preview.blocked_reason && /* @__PURE__ */ React.createElement(Alert, null, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("apply_disabled", "Apply is disabled")), /* @__PURE__ */ React.createElement(AlertDescription, null, preview.blocked_reason)),
        /* @__PURE__ */ React.createElement(
          Button,
          {
            type: "button",
            disabled: !!pending || !!preview.blocked_reason,
            onClick: () => void apply()
          },
          pending === "apply" && /* @__PURE__ */ React.createElement(Spinner, null),
          msg("apply", "Apply reviewed link")
        )
      )),
      /* @__PURE__ */ React.createElement(CardFooter, null, /* @__PURE__ */ React.createElement(Button, { type: "button", variant: "ghost", disabled: !!pending, onClick: onClose }, msg("close", "Close review")))
    );
  }
  function ReviewPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [notice, setNotice] = useState(null);
    const [selected, setSelected] = useState(null);
    const [page, setPage] = useState(0);
    const request = useRef(0);
    const form = useForm({ defaultValues: { search: "", status: "attention" } });
    const refresh = useCallback(async () => {
      const id = ++request.current;
      setLoading(true);
      setError(null);
      setSelected(null);
      try {
        const next = await host.operations.query("list_reviews");
        if (request.current === id) {
          setData(next);
          setPage(0);
        }
      } catch (error2) {
        if (request.current === id) setError(errorMessage(error2));
      } finally {
        if (request.current === id) setLoading(false);
      }
    }, []);
    useEffect(() => {
      void refresh();
      return () => {
        request.current += 1;
      };
    }, [refresh]);
    function applied(result) {
      setNotice(
        msg(
          "applied",
          "Linked {accounts, number} accounts and merged {catalogs, number} catalogs.",
          { accounts: result.linked_accounts, catalogs: result.merged_catalogs }
        )
      );
      setSelected(null);
      void refresh();
    }
    return /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "catalog-review-scroll",
        "data-scroll-restoration-id": "plugin-catalogMetadata-review"
      },
      /* @__PURE__ */ React.createElement("div", { className: "catalog-review" }, /* @__PURE__ */ React.createElement("link", { rel: "stylesheet", href: new URL("./review.css", import.meta.url).href }), /* @__PURE__ */ React.createElement("header", { className: "catalog-review-header" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h1", null, msg("title", "Catalog review")), /* @__PURE__ */ React.createElement("p", null, msg(
        "subtitle",
        "Resolve creator account links and performer conflicts. Browsing and previewing do not change Stash or the catalogs."
      ))), /* @__PURE__ */ React.createElement(
        Button,
        {
          type: "button",
          variant: "outline",
          disabled: loading || busy,
          onClick: () => void refresh()
        },
        loading && /* @__PURE__ */ React.createElement(Spinner, null),
        msg("refresh", "Refresh")
      )), /* @__PURE__ */ React.createElement("div", { className: "catalog-review-line" }, /* @__PURE__ */ React.createElement(Link, { to: "/settings/plugins" }, msg("settings", "Plugin settings")), /* @__PURE__ */ React.createElement("span", null, msg("scope", "Scene and image mapping previews remain in plugin settings."))), notice && /* @__PURE__ */ React.createElement(Alert, { role: "status" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("saved_title", "Link applied")), /* @__PURE__ */ React.createElement(AlertDescription, null, notice)), error && /* @__PURE__ */ React.createElement(Alert, { variant: "destructive", role: "alert" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("load_failed", "Could not load catalog reviews")), /* @__PURE__ */ React.createElement(AlertDescription, null, error), /* @__PURE__ */ React.createElement(
        Button,
        {
          type: "button",
          variant: "outline",
          disabled: busy || loading,
          onClick: () => void refresh()
        },
        msg("retry", "Retry")
      )), loading && !data && /* @__PURE__ */ React.createElement("p", { role: "status", className: "catalog-review-line" }, /* @__PURE__ */ React.createElement(Spinner, null), msg("loading", "Reading catalog accounts and performer evidence\u2026")), data && /* @__PURE__ */ React.createElement(React.Fragment, null, data.blocked_reason && /* @__PURE__ */ React.createElement(Alert, null, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("preview_available", "Review and preview are available")), /* @__PURE__ */ React.createElement(AlertDescription, null, data.blocked_reason)), data.unattached_conflicts.length > 0 && /* @__PURE__ */ React.createElement(Alert, { variant: "destructive" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg(
        "missing_links",
        "Some saved links reference missing accounts or performers"
      )), /* @__PURE__ */ React.createElement(AlertDescription, null, data.unattached_conflicts.map((conflict, i) => /* @__PURE__ */ React.createElement("p", { key: i }, /* @__PURE__ */ React.createElement("code", null, conflict.account_key), " \xB7 #", conflict.performer_id, ":", " ", conflict.reason)), /* @__PURE__ */ React.createElement("p", null, msg(
        "missing_links_settings",
        "Check Performer account links in plugin settings for these entries."
      )))), /* @__PURE__ */ React.createElement(FieldGroup, { className: "catalog-review-filters" }, /* @__PURE__ */ React.createElement(form.Field, { name: "search" }, (field) => /* @__PURE__ */ React.createElement(Field, null, /* @__PURE__ */ React.createElement(FieldLabel, { htmlFor: "catalog-review-search" }, msg("search", "Search catalogs")), /* @__PURE__ */ React.createElement(
        Input,
        {
          id: "catalog-review-search",
          value: field.state.value,
          disabled: busy,
          placeholder: msg(
            "search_hint",
            "Handle, account key, catalog or performer"
          ),
          onChange: (event) => {
            field.handleChange(event.target.value);
            setPage(0);
          }
        }
      ))), /* @__PURE__ */ React.createElement(form.Field, { name: "status" }, (field) => /* @__PURE__ */ React.createElement(Field, null, /* @__PURE__ */ React.createElement(FieldLabel, { htmlFor: "catalog-review-status" }, msg("show", "Show")), /* @__PURE__ */ React.createElement(
        Select,
        {
          value: field.state.value,
          disabled: busy,
          onValueChange: (value) => {
            if (value) {
              field.handleChange(value);
              setPage(0);
            }
          }
        },
        /* @__PURE__ */ React.createElement(SelectTrigger, { id: "catalog-review-status" }, /* @__PURE__ */ React.createElement(SelectValue, null, statusLabel(field.state.value))),
        /* @__PURE__ */ React.createElement(SelectContent, null, /* @__PURE__ */ React.createElement(SelectGroup, null, [
          "attention",
          "conflict",
          "candidate",
          "proposed",
          "linked",
          "unmatched",
          "all"
        ].map((value) => /* @__PURE__ */ React.createElement(SelectItem, { key: value, value }, statusLabel(value), value in data.counts ? ` (${data.counts[value]})` : ""))))
      )))), /* @__PURE__ */ React.createElement(
        "div",
        {
          className: `catalog-review-layout${selected ? " has-selection" : ""}`,
          "aria-busy": loading || busy
        },
        /* @__PURE__ */ React.createElement(form.Subscribe, { selector: (state) => state.values }, (filters) => {
          const needle = filters.search.trim().toLocaleLowerCase();
          const people = Object.fromEntries(data.performers.map((p) => [p.id, p]));
          const rows = data.catalogs.filter(
            (row) => (filters.status === "all" || filters.status === row.status || filters.status === "attention" && ["conflict", "candidate", "proposed"].includes(row.status)) && (!needle || [
              row.label,
              row.catalog_id,
              ...row.accounts.flatMap((a) => [a.account_key, ...a.handles]),
              ...row.candidate_ids.flatMap((id) => [
                id,
                people[id]?.name,
                people[id]?.disambiguation,
                ...people[id]?.alias_list ?? []
              ])
            ].some((value) => value?.toLocaleLowerCase().includes(needle)))
          );
          const currentPage = Math.min(
            page,
            Math.max(0, Math.ceil(rows.length / 12) - 1)
          );
          return /* @__PURE__ */ React.createElement(
            "section",
            {
              className: "catalog-review-stack",
              "aria-label": msg("catalogs", "Creator catalogs")
            },
            /* @__PURE__ */ React.createElement("p", { role: "status" }, msg("count", "{count, number} catalogs", { count: rows.length })),
            rows.length === 0 && /* @__PURE__ */ React.createElement("p", null, msg(
              "empty",
              "No catalogs match these filters. Try All catalogs or another search."
            )),
            rows.slice(currentPage * 12, (currentPage + 1) * 12).map((row) => /* @__PURE__ */ React.createElement(Card, { key: row.catalog_id }, /* @__PURE__ */ React.createElement(CardHeader, null, /* @__PURE__ */ React.createElement("div", { className: "catalog-review-line" }, /* @__PURE__ */ React.createElement(CardTitle, null, row.label), /* @__PURE__ */ React.createElement(
              Badge,
              {
                variant: row.status === "conflict" ? "destructive" : "secondary"
              },
              statusLabel(row.status)
            )), /* @__PURE__ */ React.createElement(CardDescription, null, row.accounts.map(
              (a) => `${a.platform}: ${a.handles.join(", ") || a.source_id}`
            ).join(" \xB7 "))), /* @__PURE__ */ React.createElement(CardContent, null, /* @__PURE__ */ React.createElement("code", null, row.catalog_id), row.candidate_ids.length > 0 && /* @__PURE__ */ React.createElement("p", null, msg("candidates", "Candidates: {names}", {
              names: row.candidate_ids.map(
                (id) => people[id] ? personLabel(people[id]) : `#${id}`
              ).join("; ")
            }))), /* @__PURE__ */ React.createElement(CardFooter, null, /* @__PURE__ */ React.createElement(
              Button,
              {
                type: "button",
                variant: "outline",
                disabled: busy || loading || selected?.catalog_id === row.catalog_id,
                onClick: () => {
                  setSelected(row);
                  setNotice(null);
                },
                "aria-label": msg("review_catalog", "Review {label}", {
                  label: row.label
                })
              },
              msg("review", "Review")
            )))),
            rows.length > 12 && /* @__PURE__ */ React.createElement(
              "nav",
              {
                className: "catalog-review-line",
                "aria-label": msg("pagination", "Catalog review pages")
              },
              /* @__PURE__ */ React.createElement(
                Button,
                {
                  type: "button",
                  variant: "outline",
                  disabled: busy || currentPage === 0,
                  onClick: () => setPage(currentPage - 1)
                },
                msg("previous", "Previous")
              ),
              /* @__PURE__ */ React.createElement("span", null, msg("page", "Page {page} of {pages}", {
                page: currentPage + 1,
                pages: Math.ceil(rows.length / 12)
              })),
              /* @__PURE__ */ React.createElement(
                Button,
                {
                  type: "button",
                  variant: "outline",
                  disabled: busy || (currentPage + 1) * 12 >= rows.length,
                  onClick: () => setPage(currentPage + 1)
                },
                msg("next", "Next")
              )
            )
          );
        }),
        selected && /* @__PURE__ */ React.createElement(
          ReviewPanel,
          {
            key: selected.catalog_id,
            row: selected,
            performers: data.performers,
            onBusy: setBusy,
            onApplied: applied,
            onClose: () => setSelected(null)
          }
        )
      )))
    );
  }
  host.routes.add({ path: "/catalogMetadata/review", component: ReviewPage });
  host.nav.add({
    to: "/catalogMetadata/review",
    label: (intl) => intl.formatMessage({ id: "catalogMetadata.review.title", defaultMessage: "Catalog review" }),
    placement: "utility"
  });
}
export {
  register as default
};
