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
    Spinner,
    Tabs,
    TabsList,
    TabsTrigger,
    TabsContent
  } = host.ui;
  const { Link } = host.router;
  const msg = (id, defaultMessage, values) => host.intl.formatMessage(
    { id: `catalogMetadata.review.${id}`, defaultMessage },
    values
  );
  const personLabel = (p) => `${p.name}${p.disambiguation ? ` (${p.disambiguation})` : ""} \xB7 #${p.id}`;
  const identityLabel = (p) => `${p.name} \xB7 ${p.id}`;
  const errorMessage = (error) => error instanceof Error ? error.message : String(error);
  const statusLabel = (status) => ({
    attention: msg("attention", "Needs review"),
    conflict: msg("conflict", "Conflicting links"),
    candidate: msg("candidate", "Name or alias match"),
    proposed: msg("proposed", "Ready to review"),
    linked: msg("linked", "Linked"),
    unmatched: msg("unmatched", "No match"),
    unlinked: msg("unlinked", "Intentionally unlinked"),
    all: msg("all_accounts", "All accounts")
  })[status];
  function Source({ account }) {
    const [details, setDetails] = useState(false);
    return /* @__PURE__ */ React.createElement("div", { className: "catalog-review-stack" }, /* @__PURE__ */ React.createElement("p", null, msg("folders", "Source folders: {folders}", {
      folders: account.directories?.join("; ") || msg("folder_unknown", "No folder recorded")
    })), account.identity_basis === "catalog-owner" && /* @__PURE__ */ React.createElement("p", null, msg(
      "inventory_owner",
      "Files are inventoried, but post metadata has not been captured. This account comes from the recorded source folder owner."
    )), !account.source_id && /* @__PURE__ */ React.createElement("p", null, msg(
      "handle_only",
      "Identified by username; a platform account ID has not been captured."
    )), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement(
      Button,
      {
        type: "button",
        variant: "ghost",
        size: "sm",
        onClick: () => setDetails(!details),
        "aria-expanded": details
      },
      details ? msg("hide_details", "Hide source identifiers") : msg("show_details", "Show source identifiers")
    )), details && /* @__PURE__ */ React.createElement("div", { className: "catalog-review-stack", "data-selectable-text": true }, /* @__PURE__ */ React.createElement("p", null, msg("account_key", "Account key"), ": ", /* @__PURE__ */ React.createElement("code", null, account.account_key)), (account.account_keys?.length ?? 0) > 1 && /* @__PURE__ */ React.createElement("p", null, msg("account_aliases", "Also recorded as"), ": ", account.account_keys.filter((key) => key !== account.account_key).map((key) => /* @__PURE__ */ React.createElement("code", { key }, key))), /* @__PURE__ */ React.createElement("p", null, msg("source_catalog", "Source catalog ID"), ":", " ", /* @__PURE__ */ React.createElement("code", null, account.catalog_id))));
  }
  function Evidence({ account, performers }) {
    return /* @__PURE__ */ React.createElement(Card, { size: "sm" }, /* @__PURE__ */ React.createElement(CardHeader, null, /* @__PURE__ */ React.createElement(CardTitle, { className: "catalog-review-line" }, /* @__PURE__ */ React.createElement(Badge, { variant: "secondary" }, account.platform), account.handles.join(", ") || account.source_id), /* @__PURE__ */ React.createElement(CardDescription, null, account.identity_name ? msg("owned_by", "Catalog performer: {name}", {
      name: account.identity_name
    }) : msg("source_account", "Source account"))), /* @__PURE__ */ React.createElement(CardContent, { className: "catalog-review-stack" }, /* @__PURE__ */ React.createElement(Source, { account }), account.evidence?.length > 0 && /* @__PURE__ */ React.createElement("ul", { className: "catalog-review-evidence" }, account.evidence.map((item, index) => {
      const p = performers.find((person) => person.id === item.performer_id);
      const kind = {
        saved_link: msg("saved", "Saved catalog link"),
        profile_url: msg("profile", "Performer profile URL"),
        name_only: msg("name_only", "Name or alias only; review required")
      }[item.kind];
      return /* @__PURE__ */ React.createElement("li", { key: `${item.kind}:${item.performer_id}:${index}` }, /* @__PURE__ */ React.createElement("span", null, kind, ": ", p ? personLabel(p) : `#${item.performer_id}`), item.url && /* @__PURE__ */ React.createElement("a", { href: item.url, target: "_blank", rel: "noreferrer" }, item.url), item.ambiguous && /* @__PURE__ */ React.createElement("span", null, msg("reused", "This handle appears on multiple account IDs.")));
    }))));
  }
  function ReviewPanel({
    row,
    identity,
    identities,
    performers,
    onClose,
    onApplied,
    onBusy
  }) {
    const binding = !!identity;
    const initialKind = row?.identity_id && !row?.performer_id ? "catalog" : "stash";
    const initial = initialKind === "catalog" ? identities.find((p) => p.id === row.identity_id) ?? null : performers.find((p) => p.id === row?.performer_id) ?? null;
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
    async function previewChoice(choice) {
      setPending("preview");
      onBusy(true);
      setError(null);
      setPreview(null);
      try {
        const related = identities.filter(
          (item) => item.id === choice.identity_id || item.id === row?.identity_id || item.stash_bindings.some((link) => link.available && link.performer_id === choice.performer_id)
        );
        const catalog_ids = [...new Set([
          row?.catalog_id,
          ...related.flatMap((item) => item.accounts.map((account) => account.catalog_id))
        ].filter(Boolean))].sort();
        const next = await host.operations.query("review_link", { ...choice, catalog_ids });
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
    const form = useForm({
      defaultValues: { kind: initialKind, target: initial },
      validators: {
        onChange: z.object({
          kind: z.enum(["stash", "catalog"]),
          target: z.object({ id: z.string().min(1) }).nullable().refine(Boolean, msg("choose", "Choose a performer."))
        })
      },
      onSubmit: async ({ value }) => {
        if (!value.target) return;
        const choice = binding ? {
          action: "bind",
          identity_id: identity.id,
          performer_id: value.target.id
        } : {
          action: "link",
          account_key: row.account_key,
          [value.kind === "stash" ? "performer_id" : "identity_id"]: value.target.id
        };
        await previewChoice(choice);
      }
    });
    async function apply() {
      if (!preview || pending || preview.blocked_reason) return;
      setPending("apply");
      onBusy(true);
      setError(null);
      try {
        const result = await host.operations.mutate("apply_link", {
          ...preview.choice,
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
    return /* @__PURE__ */ React.createElement(
      Card,
      {
        className: "catalog-review-detail",
        ref: panel,
        tabIndex: -1,
        "aria-labelledby": "catalog-review-title"
      },
      /* @__PURE__ */ React.createElement(CardHeader, null, /* @__PURE__ */ React.createElement(CardTitle, { id: "catalog-review-title" }, binding ? msg("bind_title", "Link Stash performer to {name}", {
        name: identity.name
      }) : msg("review_account", "Review {label}", { label: row.label })), /* @__PURE__ */ React.createElement(CardDescription, null, binding ? msg(
        "bind_help",
        "Keep this catalog performer\u2019s UUID and associate it with a performer in this Stash library."
      ) : msg(
        "one_account",
        "Choose who owns this source account. Each account can be reassigned independently; source catalogs and folders stay separate."
      ))),
      /* @__PURE__ */ React.createElement(CardContent, { className: "catalog-review-stack" }, binding ? /* @__PURE__ */ React.createElement("p", { "data-selectable-text": true }, msg("performer_uuid", "Catalog performer ID"), ": ", /* @__PURE__ */ React.createElement("code", null, identity.id)) : /* @__PURE__ */ React.createElement(React.Fragment, null, row.conflicts.map((conflict, i) => /* @__PURE__ */ React.createElement(Alert, { key: i, variant: "destructive" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("conflict", "Conflicting links")), /* @__PURE__ */ React.createElement(AlertDescription, null, conflict.reason))), /* @__PURE__ */ React.createElement(Evidence, { account: row, performers })), /* @__PURE__ */ React.createElement(
        "form",
        {
          onSubmit: (event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }
        },
        /* @__PURE__ */ React.createElement(FieldGroup, null, !binding && /* @__PURE__ */ React.createElement(form.Field, { name: "kind" }, (field) => /* @__PURE__ */ React.createElement(Field, null, /* @__PURE__ */ React.createElement(FieldLabel, { htmlFor: "catalog-review-target-kind" }, msg("choose_from", "Choose from")), /* @__PURE__ */ React.createElement(
          Select,
          {
            value: field.state.value,
            disabled: !!pending,
            onValueChange: (value) => {
              if (!value) return;
              field.handleChange(value);
              form.setFieldValue("target", null);
              setSearch("");
              setPreview(null);
              setError(null);
            }
          },
          /* @__PURE__ */ React.createElement(SelectTrigger, { id: "catalog-review-target-kind" }, /* @__PURE__ */ React.createElement(SelectValue, null, field.state.value === "stash" ? msg("stash_performers", "Stash performers") : msg("catalog_performers", "Catalog performers"))),
          /* @__PURE__ */ React.createElement(SelectContent, null, /* @__PURE__ */ React.createElement(SelectGroup, null, /* @__PURE__ */ React.createElement(SelectItem, { value: "stash" }, msg("stash_performers", "Stash performers")), /* @__PURE__ */ React.createElement(SelectItem, { value: "catalog" }, msg("catalog_performers", "Catalog performers"))))
        ))), /* @__PURE__ */ React.createElement(form.Subscribe, { selector: (state) => state.values.kind }, (kind) => /* @__PURE__ */ React.createElement(form.Field, { name: "target" }, (field) => {
          const invalid = field.state.meta.isTouched && !field.state.meta.isValid;
          const isStash = binding || kind === "stash";
          const label = isStash ? personLabel : identityLabel;
          const needle = search.trim().toLocaleLowerCase();
          const options = [...isStash ? performers : identities].sort(
            (a, b) => Number(row?.candidate_ids?.includes(b.id) ?? false) - Number(row?.candidate_ids?.includes(a.id) ?? false)
          ).filter(
            (p) => !needle || [
              p.id,
              p.name,
              p.disambiguation,
              ...p.alias_list ?? [],
              ...p.urls ?? []
            ].some(
              (value) => value?.toLocaleLowerCase().includes(needle)
            )
          ).slice(0, 40);
          return /* @__PURE__ */ React.createElement(Field, { "data-invalid": invalid }, /* @__PURE__ */ React.createElement(FieldLabel, { htmlFor: "catalog-review-performer" }, isStash ? msg("performer", "Stash performer") : msg("catalog_performer", "Catalog performer")), /* @__PURE__ */ React.createElement(
            Combobox,
            {
              key: kind,
              items: options,
              filter: null,
              value: field.state.value,
              disabled: !!pending,
              onValueChange: (value) => {
                field.handleChange(value);
                setPreview(null);
                setError(null);
              },
              itemToStringLabel: label,
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
            /* @__PURE__ */ React.createElement(ComboboxContent, null, /* @__PURE__ */ React.createElement(ComboboxEmpty, null, msg("no_performers", "No matching performers")), /* @__PURE__ */ React.createElement(ComboboxList, null, (p) => /* @__PURE__ */ React.createElement(ComboboxItem, { key: p.id, value: p }, /* @__PURE__ */ React.createElement("div", { className: "catalog-review-option" }, /* @__PURE__ */ React.createElement("strong", null, label(p)), p.alias_list?.length > 0 && /* @__PURE__ */ React.createElement("span", null, msg("aliases", "Aliases: {names}", {
              names: p.alias_list.join(", ")
            }))))))
          ), /* @__PURE__ */ React.createElement(FieldDescription, null, isStash ? msg(
            "stash_choice_help",
            "A new catalog UUID is created only if this Stash performer has none. Check names, aliases and profile evidence before linking."
          ) : msg(
            "catalog_choice_help",
            "Reuse an existing catalog UUID, including performers without a current Stash binding."
          )), invalid && /* @__PURE__ */ React.createElement(FieldError, { errors: field.state.meta.errors }));
        })), /* @__PURE__ */ React.createElement(Button, { type: "submit", variant: "outline", disabled: !!pending }, pending === "preview" && /* @__PURE__ */ React.createElement(Spinner, null), msg("preview", "Preview link")))
      ), !binding && /* @__PURE__ */ React.createElement(
        Button,
        {
          type: "button",
          variant: "outline",
          disabled: !!pending,
          onClick: () => void previewChoice({
            action: "unlink",
            account_key: row.account_key
          })
        },
        msg("preview_unlink", "Preview unlink")
      ), error && /* @__PURE__ */ React.createElement(Alert, { variant: "destructive", role: "alert" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("failed", "Could not complete the request")), /* @__PURE__ */ React.createElement(AlertDescription, null, error, /* @__PURE__ */ React.createElement("p", null, msg(
        "retry_preview_atomic",
        "Preview again using current data. Association changes are committed together."
      )))), preview && /* @__PURE__ */ React.createElement(
        "section",
        {
          "aria-label": msg("proposed_changes", "Proposed changes"),
          className: "catalog-review-stack"
        },
        /* @__PURE__ */ React.createElement("h3", null, preview.action === "unlink" ? msg("unlink_title", "Unlink this source account") : msg("link_to_identity", "Link to {performer}", {
          performer: preview.identity_name
        })),
        preview.action === "unlink" ? /* @__PURE__ */ React.createElement("p", null, msg(
          "unlink_help",
          "Remove this account\u2019s association. Automatic profile matching will leave it unlinked until you explicitly link it again. The catalog performer and its other accounts remain."
        )) : /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("p", null, preview.creates_identity ? msg(
          "new_uuid",
          "Create a catalog performer with a permanent UUID when you apply this link."
        ) : msg("reuse_uuid", "Use the existing catalog performer UUID.")), preview.identity_id && /* @__PURE__ */ React.createElement("p", { "data-selectable-text": true }, msg("performer_uuid", "Catalog performer ID"), ":", " ", /* @__PURE__ */ React.createElement("code", null, preview.identity_id)), preview.performer && /* @__PURE__ */ React.createElement("p", null, msg("stash_binding", "Stash binding: {name}", {
          name: personLabel(preview.performer)
        }))),
        preview.previous_identity_name && /* @__PURE__ */ React.createElement("p", null, msg("previous_owner", "Currently associated with: {name}", {
          name: preview.previous_identity_name
        })),
        preview.account && /* @__PURE__ */ React.createElement("p", null, msg("changing_account", "Account being changed: {platform} \xB7 {name}", {
          platform: preview.account.platform,
          name: preview.account.handles.join(", ") || preview.account.source_id
        })),
        (preview.account?.account_keys?.length ?? 0) > 1 && /* @__PURE__ */ React.createElement("p", null, msg("same_reddit_account", "The Reddit username and captured ID identify this same account. This decision applies to both keys.")),
        preview.associated_accounts.length > 0 && /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("p", null, msg(
          "other_accounts",
          "Other accounts already associated with this performer:"
        )), /* @__PURE__ */ React.createElement("ul", null, preview.associated_accounts.map((account) => /* @__PURE__ */ React.createElement("li", { key: account.account_key }, account.missing ? account.account_key : `${account.platform}: ${account.handles.join(", ") || account.source_id}`)))),
        /* @__PURE__ */ React.createElement("p", null, msg(
          "preserved_separate",
          "Source metadata and media stay in their existing catalogs and folders."
        )),
        preview.blocked_reason && /* @__PURE__ */ React.createElement(Alert, null, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("apply_disabled", "Apply is disabled")), /* @__PURE__ */ React.createElement(AlertDescription, null, preview.blocked_reason)),
        /* @__PURE__ */ React.createElement(
          Button,
          {
            type: "button",
            disabled: !!pending || !!preview.blocked_reason,
            onClick: () => void apply()
          },
          pending === "apply" && /* @__PURE__ */ React.createElement(Spinner, null),
          preview.action === "unlink" ? msg("apply_unlink", "Apply reviewed unlink") : msg("apply", "Apply reviewed link")
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
    const [tab, setTab] = useState("accounts");
    const [page, setPage] = useState(0);
    const request = useRef(0);
    const form = useForm({
      defaultValues: { search: "", status: "attention" }
    });
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
        request.current++;
      };
    }, [refresh]);
    function applied(result) {
      setData((current) => {
        const updates = result.updates;
        if (current.namespace !== updates.namespace) return current;
        const changed = new Map(updates.accounts.flatMap(
          (account) => (account.account_keys ?? [account.account_key]).map((key) => [key, account])
        ));
        const seen = /* @__PURE__ */ new Set();
        const accounts = current.accounts.flatMap((account) => {
          const update = changed.get(account.account_key);
          if (!update) return [account];
          if (seen.has(update.account_key)) return [];
          seen.add(update.account_key);
          const { reviewed, binding_conflicts, candidate_ids, ...association } = update;
          const conflicts = [
            ...reviewed ? [] : account.conflicts.filter(
              (conflict) => conflict.reason !== "Conflicting or missing performers; this account needs an explicit association"
            ),
            ...binding_conflicts
          ];
          const evidence = account.evidence.filter((item) => item.kind !== "saved_link").map((item) => {
            if (item.kind !== "profile_url" || !item.account_keys) return item;
            const keys = [...new Set(item.account_keys.map((key) => changed.get(key)?.account_key ?? key))];
            return { ...item, account_keys: keys, ambiguous: keys.length > 1 };
          });
          if (update.performer_id) evidence.unshift({ kind: "saved_link", performer_id: update.performer_id });
          return [{
            ...account,
            ...association,
            conflicts,
            evidence,
            label: update.handles?.join(", ") || update.source_id || account.label,
            status: conflicts.length ? "conflict" : update.status,
            candidate_ids: [.../* @__PURE__ */ new Set([...candidate_ids, ...evidence.map((item) => item.performer_id)])].sort()
          }];
        });
        const merge = (existing, changed2) => [...new Map(
          [...existing, ...changed2].map((item) => [item.id, item])
        ).values()];
        const counts = {};
        for (const account of accounts) counts[account.status] = (counts[account.status] ?? 0) + 1;
        return {
          ...current,
          accounts,
          counts,
          identities: merge(current.identities, updates.identities).sort(
            (a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id)
          ),
          performers: merge(current.performers.filter((person) => !updates.performer_ids.includes(person.id)), updates.performers),
          blocked_reason: updates.blocked_reason
        };
      });
      setNotice(
        result.action === "unlink" ? msg(
          "unlinked_notice",
          "Account unlinked. Automatic matching will respect this choice."
        ) : result.action === "bind" ? msg(
          "binding_notice",
          "Stash binding saved. The catalog performer UUID is unchanged."
        ) : msg(
          "association_notice",
          "Account linked to the catalog performer. Source catalogs remain separate."
        )
      );
      setSelected(null);
      if (data.namespace !== result.updates.namespace) void refresh();
    }
    function chooseAccount(row) {
      setSelected({ row });
      setNotice(null);
    }
    return /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "catalog-review-scroll",
        "data-scroll-restoration-id": "plugin-catalogMetadata-review"
      },
      /* @__PURE__ */ React.createElement("div", { className: "catalog-review" }, /* @__PURE__ */ React.createElement("link", { rel: "stylesheet", href: new URL("./review.css", import.meta.url).href }), /* @__PURE__ */ React.createElement("header", { className: "catalog-review-header" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h1", null, msg("title", "Catalog review")), /* @__PURE__ */ React.createElement("p", null, msg(
        "subtitle_uuids",
        "Manage catalog performers and their source accounts. Performer UUIDs persist independently of names, folders and Stash IDs."
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
      )), /* @__PURE__ */ React.createElement("div", { className: "catalog-review-line" }, /* @__PURE__ */ React.createElement(Link, { to: "/settings/plugins" }, msg("settings", "Plugin settings")), /* @__PURE__ */ React.createElement("span", null, msg(
        "read_only_browsing",
        "Browsing and previews are read-only. Apply saves the reviewed association."
      ))), notice && /* @__PURE__ */ React.createElement(Alert, { role: "status" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("saved_title", "Association saved")), /* @__PURE__ */ React.createElement(AlertDescription, null, notice)), error && /* @__PURE__ */ React.createElement(Alert, { variant: "destructive", role: "alert" }, /* @__PURE__ */ React.createElement(AlertTitle, null, msg("load_failed", "Could not load catalog reviews")), /* @__PURE__ */ React.createElement(AlertDescription, null, error), /* @__PURE__ */ React.createElement(
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
      )), /* @__PURE__ */ React.createElement(AlertDescription, null, data.unattached_conflicts.map((conflict, i) => /* @__PURE__ */ React.createElement("p", { key: i }, conflict.account_key, " \xB7 ", conflict.reason)))), /* @__PURE__ */ React.createElement(
        Tabs,
        {
          value: tab,
          onValueChange: (value) => {
            if (busy) return;
            setTab(value);
            setSelected(null);
            setPage(0);
          }
        },
        /* @__PURE__ */ React.createElement(TabsList, null, /* @__PURE__ */ React.createElement(TabsTrigger, { value: "accounts", disabled: busy }, msg("source_accounts", "Source accounts")), /* @__PURE__ */ React.createElement(TabsTrigger, { value: "performers", disabled: busy }, msg("catalog_performers", "Catalog performers"), " (", data.identities.length, ")")),
        /* @__PURE__ */ React.createElement(FieldGroup, { className: "catalog-review-filters" }, /* @__PURE__ */ React.createElement(form.Field, { name: "search" }, (field) => /* @__PURE__ */ React.createElement(Field, null, /* @__PURE__ */ React.createElement(FieldLabel, { htmlFor: "catalog-review-search" }, msg("search", "Search")), /* @__PURE__ */ React.createElement(
          Input,
          {
            id: "catalog-review-search",
            value: field.state.value,
            disabled: busy,
            placeholder: msg(
              "search_hint",
              "Name, alias, source folder or ID"
            ),
            onChange: (event) => {
              field.handleChange(event.target.value);
              setPage(0);
            }
          }
        ))), tab === "accounts" && /* @__PURE__ */ React.createElement(form.Field, { name: "status" }, (field) => /* @__PURE__ */ React.createElement(Field, null, /* @__PURE__ */ React.createElement(FieldLabel, { htmlFor: "catalog-review-status" }, msg("show", "Show")), /* @__PURE__ */ React.createElement(
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
            "unlinked",
            "unmatched",
            "all"
          ].map((value) => /* @__PURE__ */ React.createElement(SelectItem, { key: value, value }, statusLabel(value), value in data.counts ? ` (${data.counts[value]})` : ""))))
        )))),
        /* @__PURE__ */ React.createElement(
          "div",
          {
            className: selected ? "catalog-review-layout has-selection" : "catalog-review-layout",
            "aria-busy": loading || busy
          },
          /* @__PURE__ */ React.createElement(form.Subscribe, { selector: (state) => state.values }, (filters) => {
            const needle = filters.search.trim().toLocaleLowerCase();
            const people = Object.fromEntries(
              data.performers.map((p) => [p.id, p])
            );
            const matches = (values) => !needle || values.some(
              (value) => value?.toLocaleLowerCase().includes(needle)
            );
            const accounts = data.accounts.filter(
              (row) => (filters.status === "all" || filters.status === row.status || filters.status === "attention" && ["conflict", "candidate", "proposed"].includes(
                row.status
              )) && matches([
                row.label,
                row.account_key,
                ...row.account_keys ?? [],
                row.catalog_id,
                row.identity_name,
                row.identity_id,
                ...row.directories,
                ...row.handles,
                ...row.candidate_ids.flatMap((id) => [
                  id,
                  people[id]?.name,
                  people[id]?.disambiguation,
                  ...people[id]?.alias_list ?? []
                ])
              ])
            );
            const identities = data.identities.filter(
              (identity) => matches([
                identity.id,
                identity.name,
                ...identity.alias_list ?? [],
                ...identity.accounts.flatMap((a) => [
                  a.account_key,
                  ...a.account_keys ?? [],
                  ...a.handles ?? [],
                  ...a.directories ?? []
                ])
              ])
            );
            const rows = tab === "accounts" ? accounts : identities;
            const currentPage = Math.min(
              page,
              Math.max(0, Math.ceil(rows.length / 12) - 1)
            );
            return /* @__PURE__ */ React.createElement("section", { className: "catalog-review-stack" }, /* @__PURE__ */ React.createElement("p", { role: "status" }, tab === "accounts" ? msg("accounts_count", "{count, number} source accounts", {
              count: accounts.length
            }) : msg(
              "identities_count",
              "{count, number} catalog performers",
              { count: identities.length }
            )), /* @__PURE__ */ React.createElement(TabsContent, { value: "accounts", className: "catalog-review-stack" }, accounts.length === 0 && /* @__PURE__ */ React.createElement("p", null, msg(
              "empty_accounts",
              "No accounts match these filters. Try All accounts or another search."
            )), accounts.slice(currentPage * 12, (currentPage + 1) * 12).map((row) => /* @__PURE__ */ React.createElement(Card, { key: row.account_key }, /* @__PURE__ */ React.createElement(CardHeader, null, /* @__PURE__ */ React.createElement("div", { className: "catalog-review-line" }, /* @__PURE__ */ React.createElement(CardTitle, null, row.label), /* @__PURE__ */ React.createElement(
              Badge,
              {
                variant: row.status === "conflict" ? "destructive" : "secondary"
              },
              statusLabel(row.status)
            )), /* @__PURE__ */ React.createElement(CardDescription, null, row.platform, row.identity_name && ` \xB7 ${row.identity_name}`)), /* @__PURE__ */ React.createElement(CardContent, { className: "catalog-review-stack" }, /* @__PURE__ */ React.createElement(Source, { account: row }), row.candidate_ids.length > 0 && /* @__PURE__ */ React.createElement("p", null, msg("candidates", "Stash candidates: {names}", {
              names: row.candidate_ids.map(
                (id) => people[id] ? personLabel(people[id]) : `#${id}`
              ).join("; ")
            }))), /* @__PURE__ */ React.createElement(CardFooter, null, /* @__PURE__ */ React.createElement(
              Button,
              {
                type: "button",
                variant: "outline",
                disabled: busy || loading || selected?.row?.account_key === row.account_key,
                onClick: () => chooseAccount(row),
                "aria-label": msg(
                  "review_account",
                  "Review {label}",
                  { label: row.label }
                )
              },
              msg("review", "Review")
            ))))), /* @__PURE__ */ React.createElement(
              TabsContent,
              {
                value: "performers",
                className: "catalog-review-stack"
              },
              identities.length === 0 && /* @__PURE__ */ React.createElement("p", null, msg(
                "empty_identities",
                "Catalog performers appear when accounts are linked or existing associations are migrated."
              )),
              identities.slice(currentPage * 12, (currentPage + 1) * 12).map((identity) => /* @__PURE__ */ React.createElement(Card, { key: identity.id }, /* @__PURE__ */ React.createElement(CardHeader, null, /* @__PURE__ */ React.createElement(CardTitle, null, identity.name), /* @__PURE__ */ React.createElement(CardDescription, null, msg(
                "associated_count",
                "{count, plural, one {# associated account} other {# associated accounts}}",
                { count: identity.accounts.length }
              ))), /* @__PURE__ */ React.createElement(CardContent, { className: "catalog-review-stack" }, /* @__PURE__ */ React.createElement("p", { "data-selectable-text": true }, msg("performer_uuid", "Catalog performer ID"), ":", " ", /* @__PURE__ */ React.createElement("code", null, identity.id)), identity.alias_list?.length > 0 && /* @__PURE__ */ React.createElement("p", null, msg("aliases", "Aliases: {names}", {
                names: identity.alias_list.join(", ")
              })), identity.stash_bindings.map((binding) => /* @__PURE__ */ React.createElement(
                "p",
                {
                  key: `${binding.namespace}:${binding.performer_id}`
                },
                msg(
                  "library_binding",
                  "Stash library {namespace}: {name} \xB7 #{id}",
                  {
                    namespace: binding.namespace,
                    name: binding.name ?? "",
                    id: binding.performer_id
                  }
                ),
                binding.redirect_to && ` \u2192 #${binding.redirect_to}`
              )), identity.accounts.map((account) => /* @__PURE__ */ React.createElement(Card, { size: "sm", key: account.account_key }, /* @__PURE__ */ React.createElement(CardHeader, null, /* @__PURE__ */ React.createElement(CardTitle, null, account.platform ?? "", " \xB7", " ", account.handles?.join(", ") || account.account_key)), /* @__PURE__ */ React.createElement(CardContent, null, account.missing ? /* @__PURE__ */ React.createElement("p", null, msg(
                "missing_account",
                "Source account is not currently present in an active catalog. Its association is retained."
              )) : /* @__PURE__ */ React.createElement(Source, { account })), /* @__PURE__ */ React.createElement(CardFooter, null, /* @__PURE__ */ React.createElement(
                Button,
                {
                  type: "button",
                  variant: "outline",
                  disabled: busy || loading || account.missing,
                  onClick: () => chooseAccount(
                    data.accounts.find(
                      (row) => row.account_key === account.account_key
                    )
                  )
                },
                msg("manage_account", "Manage account")
              ))))), /* @__PURE__ */ React.createElement(CardFooter, null, identity.stash_bindings.some(
                (binding) => binding.available
              ) ? /* @__PURE__ */ React.createElement(Badge, { variant: "secondary" }, msg("linked_to_stash", "Linked to Stash")) : /* @__PURE__ */ React.createElement(
                Button,
                {
                  type: "button",
                  variant: "outline",
                  disabled: busy || loading,
                  onClick: () => {
                    setSelected({ identity });
                    setNotice(null);
                  }
                },
                msg("manage_binding", "Link Stash performer")
              ))))
            ), rows.length > 12 && /* @__PURE__ */ React.createElement(
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
            ));
          }),
          selected && /* @__PURE__ */ React.createElement(
            ReviewPanel,
            {
              key: selected.row?.account_key ?? selected.identity.id,
              row: selected.row,
              identity: selected.identity,
              identities: data.identities,
              performers: data.performers,
              onBusy: setBusy,
              onApplied: applied,
              onClose: () => setSelected(null)
            }
          )
        )
      )))
    );
  }
  host.routes.add({ path: "/catalogMetadata/review", component: ReviewPage });
  host.nav.add({
    to: "/catalogMetadata/review",
    label: (intl) => intl.formatMessage({
      id: "catalogMetadata.review.title",
      defaultMessage: "Catalog review"
    }),
    placement: "utility"
  });
}
export {
  register as default
};
