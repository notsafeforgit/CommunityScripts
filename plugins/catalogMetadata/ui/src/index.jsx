// Build with ui/build.sh. React, forms and controls come from the Stash host.
export default function register(host) {
  if (host.version !== "1" || !host.react || !host.forms || !host.operations) {
    throw new Error(
      "Catalog review requires the current Stash v3 plugin UI host. Update Stash first.",
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
    TabsContent,
  } = host.ui;
  const { Link } = host.router;
  const msg = (id, defaultMessage, values) =>
    host.intl.formatMessage(
      { id: `catalogMetadata.review.${id}`, defaultMessage },
      values,
    );
  const personLabel = (p) =>
    `${p.name}${p.disambiguation ? ` (${p.disambiguation})` : ""} · #${p.id}`;
  const identityLabel = (p) => `${p.name} · ${p.id}`;
  const errorMessage = (error) =>
    error instanceof Error ? error.message : String(error);
  const statusLabel = (status) =>
    ({
      attention: msg("attention", "Needs review"),
      conflict: msg("conflict", "Conflicting links"),
      candidate: msg("candidate", "Name or alias match"),
      proposed: msg("proposed", "Ready to review"),
      linked: msg("linked", "Linked"),
      unmatched: msg("unmatched", "No match"),
      unlinked: msg("unlinked", "Intentionally unlinked"),
      all: msg("all_accounts", "All accounts"),
    })[status];

  function Source({ account }) {
    const [details, setDetails] = useState(false);
    return (
      <div className="catalog-review-stack">
        <p>
          {msg("folders", "Source folders: {folders}", {
            folders:
              account.directories?.join("; ") ||
              msg("folder_unknown", "No folder recorded"),
          })}
        </p>
        {account.identity_basis === "catalog-owner" && (
          <p>
            {msg(
              "inventory_owner",
              "Files are inventoried, but post metadata has not been captured. This account comes from the recorded source folder owner.",
            )}
          </p>
        )}
        {!account.source_id && (
          <p>
            {msg(
              "handle_only",
              "Identified by username; a platform account ID has not been captured.",
            )}
          </p>
        )}
        <div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setDetails(!details)}
            aria-expanded={details}
          >
            {details
              ? msg("hide_details", "Hide source identifiers")
              : msg("show_details", "Show source identifiers")}
          </Button>
        </div>
        {details && (
          <div className="catalog-review-stack" data-selectable-text>
            <p>
              {msg("account_key", "Account key")}: <code>{account.account_key}</code>
            </p>
            {(account.account_keys?.length ?? 0) > 1 && (
              <p>
                {msg("account_aliases", "Also recorded as")}: {account.account_keys
                  .filter((key) => key !== account.account_key)
                  .map((key) => <code key={key}>{key}</code>)}
              </p>
            )}
            <p>
              {msg("source_catalog", "Source catalog ID")}:{" "}
              <code>{account.catalog_id}</code>
            </p>
          </div>
        )}
      </div>
    );
  }

  function Evidence({ account, performers }) {
    return (
      <Card size="sm">
        <CardHeader>
          <CardTitle className="catalog-review-line">
            <Badge variant="secondary">{account.platform}</Badge>
            {account.handles.join(", ") || account.source_id}
          </CardTitle>
          <CardDescription>
            {account.identity_name
              ? msg("owned_by", "Catalog performer: {name}", {
                  name: account.identity_name,
                })
              : msg("source_account", "Source account")}
          </CardDescription>
        </CardHeader>
        <CardContent className="catalog-review-stack">
          <Source account={account} />
          {account.evidence?.length > 0 && (
            <ul className="catalog-review-evidence">
              {account.evidence.map((item, index) => {
                const p = performers.find((person) => person.id === item.performer_id);
                const kind = {
                  saved_link: msg("saved", "Saved catalog link"),
                  profile_url: msg("profile", "Performer profile URL"),
                  name_only: msg("name_only", "Name or alias only; review required"),
                }[item.kind];
                return (
                  <li key={`${item.kind}:${item.performer_id}:${index}`}>
                    <span>
                      {kind}: {p ? personLabel(p) : `#${item.performer_id}`}
                    </span>
                    {item.url && (
                      <a href={item.url} target="_blank" rel="noreferrer">
                        {item.url}
                      </a>
                    )}
                    {item.ambiguous && (
                      <span>
                        {msg("reused", "This handle appears on multiple account IDs.")}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    );
  }

  function ReviewPanel({
    row,
    identity,
    identities,
    performers,
    onClose,
    onApplied,
    onBusy,
  }) {
    const binding = !!identity;
    const initialKind = row?.identity_id && !row?.performer_id ? "catalog" : "stash";
    const initial =
      initialKind === "catalog"
        ? (identities.find((p) => p.id === row.identity_id) ?? null)
        : (performers.find((p) => p.id === row?.performer_id) ?? null);
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
        const related = identities.filter((item) =>
          item.id === choice.identity_id || item.id === row?.identity_id ||
          item.stash_bindings.some((link) => link.available && link.performer_id === choice.performer_id),
        );
        const catalog_ids = [...new Set([
          row?.catalog_id,
          ...related.flatMap((item) => item.accounts.map((account) => account.catalog_id)),
        ].filter(Boolean))].sort();
        const next = await host.operations.query("review_link", { ...choice, catalog_ids });
        if (alive.current) setPreview(next);
      } catch (error) {
        if (alive.current) setError(errorMessage(error));
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
          target: z
            .object({ id: z.string().min(1) })
            .nullable()
            .refine(Boolean, msg("choose", "Choose a performer.")),
        }),
      },
      onSubmit: async ({ value }) => {
        if (!value.target) return;
        const choice = binding
          ? {
              action: "bind",
              identity_id: identity.id,
              performer_id: value.target.id,
            }
          : {
              action: "link",
              account_key: row.account_key,
              [value.kind === "stash" ? "performer_id" : "identity_id"]: value.target.id,
            };
        await previewChoice(choice);
      },
    });
    async function apply() {
      if (!preview || pending || preview.blocked_reason) return;
      setPending("apply");
      onBusy(true);
      setError(null);
      try {
        const result = await host.operations.mutate("apply_link", {
          ...preview.choice,
          review_token: preview.review_token,
        });
        if (alive.current) onApplied(result);
      } catch (error) {
        if (alive.current) {
          setError(errorMessage(error));
          setPreview(null);
        }
      } finally {
        if (alive.current) setPending(null);
        onBusy(false);
      }
    }
    return (
      <Card
        className="catalog-review-detail"
        ref={panel}
        tabIndex={-1}
        aria-labelledby="catalog-review-title"
      >
        <CardHeader>
          <CardTitle id="catalog-review-title">
            {binding
              ? msg("bind_title", "Link Stash performer to {name}", {
                  name: identity.name,
                })
              : msg("review_account", "Review {label}", { label: row.label })}
          </CardTitle>
          <CardDescription>
            {binding
              ? msg(
                  "bind_help",
                  "Keep this catalog performer’s UUID and associate it with a performer in this Stash library.",
                )
              : msg(
                  "one_account",
                  "Choose who owns this source account. Each account can be reassigned independently; source catalogs and folders stay separate.",
                )}
          </CardDescription>
        </CardHeader>
        <CardContent className="catalog-review-stack">
          {binding ? (
            <p data-selectable-text>
              {msg("performer_uuid", "Catalog performer ID")}: <code>{identity.id}</code>
            </p>
          ) : (
            <>
              {row.conflicts.map((conflict, i) => (
                <Alert key={i} variant="destructive">
                  <AlertTitle>{msg("conflict", "Conflicting links")}</AlertTitle>
                  <AlertDescription>{conflict.reason}</AlertDescription>
                </Alert>
              ))}
              <Evidence account={row} performers={performers} />
            </>
          )}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              event.stopPropagation();
              void form.handleSubmit();
            }}
          >
            <FieldGroup>
              {!binding && (
                <form.Field name="kind">
                  {(field) => (
                    <Field>
                      <FieldLabel htmlFor="catalog-review-target-kind">
                        {msg("choose_from", "Choose from")}
                      </FieldLabel>
                      <Select
                        value={field.state.value}
                        disabled={!!pending}
                        onValueChange={(value) => {
                          if (!value) return;
                          field.handleChange(value);
                          form.setFieldValue("target", null);
                          setSearch("");
                          setPreview(null);
                          setError(null);
                        }}
                      >
                        <SelectTrigger id="catalog-review-target-kind">
                          <SelectValue>
                            {field.state.value === "stash"
                              ? msg("stash_performers", "Stash performers")
                              : msg("catalog_performers", "Catalog performers")}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectGroup>
                            <SelectItem value="stash">
                              {msg("stash_performers", "Stash performers")}
                            </SelectItem>
                            <SelectItem value="catalog">
                              {msg("catalog_performers", "Catalog performers")}
                            </SelectItem>
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                    </Field>
                  )}
                </form.Field>
              )}
              <form.Subscribe selector={(state) => state.values.kind}>
                {(kind) => (
                  <form.Field name="target">
                    {(field) => {
                      const invalid =
                        field.state.meta.isTouched && !field.state.meta.isValid;
                      const isStash = binding || kind === "stash";
                      const label = isStash ? personLabel : identityLabel;
                      const needle = search.trim().toLocaleLowerCase();
                      const options = [...(isStash ? performers : identities)]
                        .sort(
                          (a, b) =>
                            Number(row?.candidate_ids?.includes(b.id) ?? false) -
                            Number(row?.candidate_ids?.includes(a.id) ?? false),
                        )
                        .filter(
                          (p) =>
                            !needle ||
                            [
                              p.id,
                              p.name,
                              p.disambiguation,
                              ...(p.alias_list ?? []),
                              ...(p.urls ?? []),
                            ].some((value) =>
                              value?.toLocaleLowerCase().includes(needle),
                            ),
                        )
                        .slice(0, 40);
                      return (
                        <Field data-invalid={invalid}>
                          <FieldLabel htmlFor="catalog-review-performer">
                            {isStash
                              ? msg("performer", "Stash performer")
                              : msg("catalog_performer", "Catalog performer")}
                          </FieldLabel>
                          <Combobox
                            key={kind}
                            items={options}
                            filter={null}
                            value={field.state.value}
                            disabled={!!pending}
                            onValueChange={(value) => {
                              field.handleChange(value);
                              setPreview(null);
                              setError(null);
                            }}
                            itemToStringLabel={label}
                            itemToStringValue={(p) => p.id}
                            isItemEqualToValue={(a, b) => a.id === b.id}
                            onOpenChange={(open) => {
                              if (open) setSearch("");
                            }}
                            onInputValueChange={(value, details) => {
                              if (
                                ["input-change", "input-clear"].includes(details.reason)
                              )
                                setSearch(value);
                            }}
                          >
                            <ComboboxInput
                              id="catalog-review-performer"
                              showClear
                              onBlur={field.handleBlur}
                              aria-invalid={invalid}
                              placeholder={msg(
                                "search_performers",
                                "Search names, aliases, profile URLs or IDs",
                              )}
                            />
                            <ComboboxContent>
                              <ComboboxEmpty>
                                {msg("no_performers", "No matching performers")}
                              </ComboboxEmpty>
                              <ComboboxList>
                                {(p) => (
                                  <ComboboxItem key={p.id} value={p}>
                                    <div className="catalog-review-option">
                                      <strong>{label(p)}</strong>
                                      {p.alias_list?.length > 0 && (
                                        <span>
                                          {msg("aliases", "Aliases: {names}", {
                                            names: p.alias_list.join(", "),
                                          })}
                                        </span>
                                      )}
                                    </div>
                                  </ComboboxItem>
                                )}
                              </ComboboxList>
                            </ComboboxContent>
                          </Combobox>
                          <FieldDescription>
                            {isStash
                              ? msg(
                                  "stash_choice_help",
                                  "A new catalog UUID is created only if this Stash performer has none. Check names, aliases and profile evidence before linking.",
                                )
                              : msg(
                                  "catalog_choice_help",
                                  "Reuse an existing catalog UUID, including performers without a current Stash binding.",
                                )}
                          </FieldDescription>
                          {invalid && <FieldError errors={field.state.meta.errors} />}
                        </Field>
                      );
                    }}
                  </form.Field>
                )}
              </form.Subscribe>
              <Button type="submit" variant="outline" disabled={!!pending}>
                {pending === "preview" && <Spinner />}
                {msg("preview", "Preview link")}
              </Button>
            </FieldGroup>
          </form>
          {!binding && (
            <Button
              type="button"
              variant="outline"
              disabled={!!pending}
              onClick={() =>
                void previewChoice({
                  action: "unlink",
                  account_key: row.account_key,
                })
              }
            >
              {msg("preview_unlink", "Preview unlink")}
            </Button>
          )}
          {error && (
            <Alert variant="destructive" role="alert">
              <AlertTitle>{msg("failed", "Could not complete the request")}</AlertTitle>
              <AlertDescription>
                {error}
                <p>
                  {msg(
                    "retry_preview_atomic",
                    "Preview again using current data. Association changes are committed together.",
                  )}
                </p>
              </AlertDescription>
            </Alert>
          )}
          {preview && (
            <section
              aria-label={msg("proposed_changes", "Proposed changes")}
              className="catalog-review-stack"
            >
              <h3>
                {preview.action === "unlink"
                  ? msg("unlink_title", "Unlink this source account")
                  : msg("link_to_identity", "Link to {performer}", {
                      performer: preview.identity_name,
                    })}
              </h3>
              {preview.action === "unlink" ? (
                <p>
                  {msg(
                    "unlink_help",
                    "Remove this account’s association. Automatic profile matching will leave it unlinked until you explicitly link it again. The catalog performer and its other accounts remain.",
                  )}
                </p>
              ) : (
                <>
                  <p>
                    {preview.creates_identity
                      ? msg(
                          "new_uuid",
                          "Create a catalog performer with a permanent UUID when you apply this link.",
                        )
                      : msg("reuse_uuid", "Use the existing catalog performer UUID.")}
                  </p>
                  {preview.identity_id && (
                    <p data-selectable-text>
                      {msg("performer_uuid", "Catalog performer ID")}:{" "}
                      <code>{preview.identity_id}</code>
                    </p>
                  )}
                  {preview.performer && (
                    <p>
                      {msg("stash_binding", "Stash binding: {name}", {
                        name: personLabel(preview.performer),
                      })}
                    </p>
                  )}
                </>
              )}
              {preview.previous_identity_name && (
                <p>
                  {msg("previous_owner", "Currently associated with: {name}", {
                    name: preview.previous_identity_name,
                  })}
                </p>
              )}
              {preview.account && (
                <p>
                  {msg("changing_account", "Account being changed: {platform} · {name}", {
                    platform: preview.account.platform,
                    name: preview.account.handles.join(", ") || preview.account.source_id,
                  })}
                </p>
              )}
              {(preview.account?.account_keys?.length ?? 0) > 1 && (
                <p>
                  {msg("same_reddit_account", "The Reddit username and captured ID identify this same account. This decision applies to both keys.")}
                </p>
              )}
              {preview.associated_accounts.length > 0 && (
                <div>
                  <p>
                    {msg(
                      "other_accounts",
                      "Other accounts already associated with this performer:",
                    )}
                  </p>
                  <ul>
                    {preview.associated_accounts.map((account) => (
                      <li key={account.account_key}>
                        {account.missing
                          ? account.account_key
                          : `${account.platform}: ${account.handles.join(", ") || account.source_id}`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p>
                {msg(
                  "preserved_separate",
                  "Source metadata and media stay in their existing catalogs and folders.",
                )}
              </p>
              {preview.blocked_reason && (
                <Alert>
                  <AlertTitle>{msg("apply_disabled", "Apply is disabled")}</AlertTitle>
                  <AlertDescription>{preview.blocked_reason}</AlertDescription>
                </Alert>
              )}
              <Button
                type="button"
                disabled={!!pending || !!preview.blocked_reason}
                onClick={() => void apply()}
              >
                {pending === "apply" && <Spinner />}
                {preview.action === "unlink"
                  ? msg("apply_unlink", "Apply reviewed unlink")
                  : msg("apply", "Apply reviewed link")}
              </Button>
            </section>
          )}
        </CardContent>
        <CardFooter>
          <Button type="button" variant="ghost" disabled={!!pending} onClick={onClose}>
            {msg("close", "Close review")}
          </Button>
        </CardFooter>
      </Card>
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
      defaultValues: { search: "", status: "attention" },
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
      } catch (error) {
        if (request.current === id) setError(errorMessage(error));
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
        const changed = new Map(updates.accounts.flatMap((account) =>
          (account.account_keys ?? [account.account_key]).map((key) => [key, account]),
        ));
        const seen = new Set();
        const accounts = current.accounts.flatMap((account) => {
          const update = changed.get(account.account_key);
          if (!update) return [account];
          if (seen.has(update.account_key)) return [];
          seen.add(update.account_key);
          const { reviewed, binding_conflicts, candidate_ids, ...association } = update;
          // Explicit decisions resolve ownership conflicts. For automatic links,
          // preserve other evidence until the user requests a discovery refresh.
          const conflicts = [
            ...(reviewed ? [] : account.conflicts.filter((conflict) =>
              conflict.reason !== "Conflicting or missing performers; this account needs an explicit association",
            )),
            ...binding_conflicts,
          ];
          const evidence = account.evidence.filter((item) => item.kind !== "saved_link").map((item) => {
            if (item.kind !== "profile_url" || !item.account_keys) return item;
            const keys = [...new Set(item.account_keys.map((key) => changed.get(key)?.account_key ?? key))];
            return { ...item, account_keys: keys, ambiguous: keys.length > 1 };
          });
          if (update.performer_id) evidence.unshift({ kind: "saved_link", performer_id: update.performer_id });
          return [{
            ...account, ...association, conflicts, evidence,
            label: update.handles?.join(", ") || update.source_id || account.label,
            status: conflicts.length ? "conflict" : update.status,
            candidate_ids: [...new Set([...candidate_ids, ...evidence.map((item) => item.performer_id)])].sort(),
          }];
        });
        const merge = (existing, changed) => [...new Map(
          [...existing, ...changed].map((item) => [item.id, item]),
        ).values()];
        const counts = {};
        for (const account of accounts) counts[account.status] = (counts[account.status] ?? 0) + 1;
        return {
          ...current, accounts, counts,
          identities: merge(current.identities, updates.identities).sort((a, b) =>
            a.name.localeCompare(b.name) || a.id.localeCompare(b.id),
          ),
          performers: merge(current.performers.filter((person) => !updates.performer_ids.includes(person.id)), updates.performers),
          blocked_reason: updates.blocked_reason,
        };
      });
      setNotice(
        result.action === "unlink"
          ? msg(
              "unlinked_notice",
              "Account unlinked. Automatic matching will respect this choice.",
            )
          : result.action === "bind"
            ? msg(
                "binding_notice",
                "Stash binding saved. The catalog performer UUID is unchanged.",
              )
            : msg(
                "association_notice",
                "Account linked to the catalog performer. Source catalogs remain separate.",
              ),
      );
      setSelected(null);
      if (data.namespace !== result.updates.namespace) void refresh();
    }
    function chooseAccount(row) {
      setSelected({ row });
      setNotice(null);
    }
    return (
      <div
        className="catalog-review-scroll"
        data-scroll-restoration-id="plugin-catalogMetadata-review"
      >
        <div className="catalog-review">
          <link rel="stylesheet" href={new URL("./review.css", import.meta.url).href} />
          <header className="catalog-review-header">
            <div>
              <h1>{msg("title", "Catalog review")}</h1>
              <p>
                {msg(
                  "subtitle_uuids",
                  "Manage catalog performers and their source accounts. Performer UUIDs persist independently of names, folders and Stash IDs.",
                )}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={loading || busy}
              onClick={() => void refresh()}
            >
              {loading && <Spinner />}
              {msg("refresh", "Refresh")}
            </Button>
          </header>
          <div className="catalog-review-line">
            <Link to="/settings/plugins">{msg("settings", "Plugin settings")}</Link>
            <span>
              {msg(
                "read_only_browsing",
                "Browsing and previews are read-only. Apply saves the reviewed association.",
              )}
            </span>
          </div>
          {notice && (
            <Alert role="status">
              <AlertTitle>{msg("saved_title", "Association saved")}</AlertTitle>
              <AlertDescription>{notice}</AlertDescription>
            </Alert>
          )}
          {error && (
            <Alert variant="destructive" role="alert">
              <AlertTitle>
                {msg("load_failed", "Could not load catalog reviews")}
              </AlertTitle>
              <AlertDescription>{error}</AlertDescription>
              <Button
                type="button"
                variant="outline"
                disabled={busy || loading}
                onClick={() => void refresh()}
              >
                {msg("retry", "Retry")}
              </Button>
            </Alert>
          )}
          {loading && !data && (
            <p role="status" className="catalog-review-line">
              <Spinner />
              {msg("loading", "Reading catalog accounts and performer evidence…")}
            </p>
          )}
          {data && (
            <>
              {data.blocked_reason && (
                <Alert>
                  <AlertTitle>
                    {msg("preview_available", "Review and preview are available")}
                  </AlertTitle>
                  <AlertDescription>{data.blocked_reason}</AlertDescription>
                </Alert>
              )}
              {data.unattached_conflicts.length > 0 && (
                <Alert variant="destructive">
                  <AlertTitle>
                    {msg(
                      "missing_links",
                      "Some saved links reference missing accounts or performers",
                    )}
                  </AlertTitle>
                  <AlertDescription>
                    {data.unattached_conflicts.map((conflict, i) => (
                      <p key={i}>
                        {conflict.account_key} · {conflict.reason}
                      </p>
                    ))}
                  </AlertDescription>
                </Alert>
              )}
              <Tabs
                value={tab}
                onValueChange={(value) => {
                  if (busy) return;
                  setTab(value);
                  setSelected(null);
                  setPage(0);
                }}
              >
                <TabsList>
                  <TabsTrigger value="accounts" disabled={busy}>
                    {msg("source_accounts", "Source accounts")}
                  </TabsTrigger>
                  <TabsTrigger value="performers" disabled={busy}>
                    {msg("catalog_performers", "Catalog performers")} (
                    {data.identities.length})
                  </TabsTrigger>
                </TabsList>
                <FieldGroup className="catalog-review-filters">
                  <form.Field name="search">
                    {(field) => (
                      <Field>
                        <FieldLabel htmlFor="catalog-review-search">
                          {msg("search", "Search")}
                        </FieldLabel>
                        <Input
                          id="catalog-review-search"
                          value={field.state.value}
                          disabled={busy}
                          placeholder={msg(
                            "search_hint",
                            "Name, alias, source folder or ID",
                          )}
                          onChange={(event) => {
                            field.handleChange(event.target.value);
                            setPage(0);
                          }}
                        />
                      </Field>
                    )}
                  </form.Field>
                  {tab === "accounts" && (
                    <form.Field name="status">
                      {(field) => (
                        <Field>
                          <FieldLabel htmlFor="catalog-review-status">
                            {msg("show", "Show")}
                          </FieldLabel>
                          <Select
                            value={field.state.value}
                            disabled={busy}
                            onValueChange={(value) => {
                              if (value) {
                                field.handleChange(value);
                                setPage(0);
                              }
                            }}
                          >
                            <SelectTrigger id="catalog-review-status">
                              <SelectValue>{statusLabel(field.state.value)}</SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                {[
                                  "attention",
                                  "conflict",
                                  "candidate",
                                  "proposed",
                                  "linked",
                                  "unlinked",
                                  "unmatched",
                                  "all",
                                ].map((value) => (
                                  <SelectItem key={value} value={value}>
                                    {statusLabel(value)}
                                    {value in data.counts
                                      ? ` (${data.counts[value]})`
                                      : ""}
                                  </SelectItem>
                                ))}
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                        </Field>
                      )}
                    </form.Field>
                  )}
                </FieldGroup>
                <div
                  className={
                    selected
                      ? "catalog-review-layout has-selection"
                      : "catalog-review-layout"
                  }
                  aria-busy={loading || busy}
                >
                  <form.Subscribe selector={(state) => state.values}>
                    {(filters) => {
                      const needle = filters.search.trim().toLocaleLowerCase();
                      const people = Object.fromEntries(
                        data.performers.map((p) => [p.id, p]),
                      );
                      const matches = (values) =>
                        !needle ||
                        values.some((value) =>
                          value?.toLocaleLowerCase().includes(needle),
                        );
                      const accounts = data.accounts.filter(
                        (row) =>
                          (filters.status === "all" ||
                            filters.status === row.status ||
                            (filters.status === "attention" &&
                              ["conflict", "candidate", "proposed"].includes(
                                row.status,
                              ))) &&
                          matches([
                            row.label,
                            row.account_key,
                            ...(row.account_keys ?? []),
                            row.catalog_id,
                            row.identity_name,
                            row.identity_id,
                            ...row.directories,
                            ...row.handles,
                            ...row.candidate_ids.flatMap((id) => [
                              id,
                              people[id]?.name,
                              people[id]?.disambiguation,
                              ...(people[id]?.alias_list ?? []),
                            ]),
                          ]),
                      );
                      const identities = data.identities.filter((identity) =>
                        matches([
                          identity.id,
                          identity.name,
                          ...(identity.alias_list ?? []),
                          ...identity.accounts.flatMap((a) => [
                            a.account_key,
                            ...(a.account_keys ?? []),
                            ...(a.handles ?? []),
                            ...(a.directories ?? []),
                          ]),
                        ]),
                      );
                      const rows = tab === "accounts" ? accounts : identities;
                      const currentPage = Math.min(
                        page,
                        Math.max(0, Math.ceil(rows.length / 12) - 1),
                      );
                      return (
                        <section className="catalog-review-stack">
                          <p role="status">
                            {tab === "accounts"
                              ? msg("accounts_count", "{count, number} source accounts", {
                                  count: accounts.length,
                                })
                              : msg(
                                  "identities_count",
                                  "{count, number} catalog performers",
                                  { count: identities.length },
                                )}
                          </p>
                          <TabsContent value="accounts" className="catalog-review-stack">
                            {accounts.length === 0 && (
                              <p>
                                {msg(
                                  "empty_accounts",
                                  "No accounts match these filters. Try All accounts or another search.",
                                )}
                              </p>
                            )}
                            {accounts
                              .slice(currentPage * 12, (currentPage + 1) * 12)
                              .map((row) => (
                                <Card key={row.account_key}>
                                  <CardHeader>
                                    <div className="catalog-review-line">
                                      <CardTitle>{row.label}</CardTitle>
                                      <Badge
                                        variant={
                                          row.status === "conflict"
                                            ? "destructive"
                                            : "secondary"
                                        }
                                      >
                                        {statusLabel(row.status)}
                                      </Badge>
                                    </div>
                                    <CardDescription>
                                      {row.platform}
                                      {row.identity_name && ` · ${row.identity_name}`}
                                    </CardDescription>
                                  </CardHeader>
                                  <CardContent className="catalog-review-stack">
                                    <Source account={row} />
                                    {row.candidate_ids.length > 0 && (
                                      <p>
                                        {msg("candidates", "Stash candidates: {names}", {
                                          names: row.candidate_ids
                                            .map((id) =>
                                              people[id]
                                                ? personLabel(people[id])
                                                : `#${id}`,
                                            )
                                            .join("; "),
                                        })}
                                      </p>
                                    )}
                                  </CardContent>
                                  <CardFooter>
                                    <Button
                                      type="button"
                                      variant="outline"
                                      disabled={
                                        busy ||
                                        loading ||
                                        selected?.row?.account_key === row.account_key
                                      }
                                      onClick={() => chooseAccount(row)}
                                      aria-label={msg(
                                        "review_account",
                                        "Review {label}",
                                        { label: row.label },
                                      )}
                                    >
                                      {msg("review", "Review")}
                                    </Button>
                                  </CardFooter>
                                </Card>
                              ))}
                          </TabsContent>
                          <TabsContent
                            value="performers"
                            className="catalog-review-stack"
                          >
                            {identities.length === 0 && (
                              <p>
                                {msg(
                                  "empty_identities",
                                  "Catalog performers appear when accounts are linked or existing associations are migrated.",
                                )}
                              </p>
                            )}
                            {identities
                              .slice(currentPage * 12, (currentPage + 1) * 12)
                              .map((identity) => (
                                <Card key={identity.id}>
                                  <CardHeader>
                                    <CardTitle>{identity.name}</CardTitle>
                                    <CardDescription>
                                      {msg(
                                        "associated_count",
                                        "{count, plural, one {# associated account} other {# associated accounts}}",
                                        { count: identity.accounts.length },
                                      )}
                                    </CardDescription>
                                  </CardHeader>
                                  <CardContent className="catalog-review-stack">
                                    <p data-selectable-text>
                                      {msg("performer_uuid", "Catalog performer ID")}:{" "}
                                      <code>{identity.id}</code>
                                    </p>
                                    {identity.alias_list?.length > 0 && (
                                      <p>
                                        {msg("aliases", "Aliases: {names}", {
                                          names: identity.alias_list.join(", "),
                                        })}
                                      </p>
                                    )}
                                    {identity.stash_bindings.map((binding) => (
                                      <p
                                        key={`${binding.namespace}:${binding.performer_id}`}
                                      >
                                        {msg(
                                          "library_binding",
                                          "Stash library {namespace}: {name} · #{id}",
                                          {
                                            namespace: binding.namespace,
                                            name: binding.name ?? "",
                                            id: binding.performer_id,
                                          },
                                        )}
                                        {binding.redirect_to &&
                                          ` → #${binding.redirect_to}`}
                                      </p>
                                    ))}
                                    {identity.accounts.map((account) => (
                                      <Card size="sm" key={account.account_key}>
                                        <CardHeader>
                                          <CardTitle>
                                            {account.platform ?? ""} ·{" "}
                                            {account.handles?.join(", ") ||
                                              account.account_key}
                                          </CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                          {account.missing ? (
                                            <p>
                                              {msg(
                                                "missing_account",
                                                "Source account is not currently present in an active catalog. Its association is retained.",
                                              )}
                                            </p>
                                          ) : (
                                            <Source account={account} />
                                          )}
                                        </CardContent>
                                        <CardFooter>
                                          <Button
                                            type="button"
                                            variant="outline"
                                            disabled={busy || loading || account.missing}
                                            onClick={() =>
                                              chooseAccount(
                                                data.accounts.find(
                                                  (row) =>
                                                    row.account_key ===
                                                    account.account_key,
                                                ),
                                              )
                                            }
                                          >
                                            {msg("manage_account", "Manage account")}
                                          </Button>
                                        </CardFooter>
                                      </Card>
                                    ))}
                                  </CardContent>
                                  <CardFooter>
                                    {identity.stash_bindings.some(
                                      (binding) => binding.available,
                                    ) ? (
                                      <Badge variant="secondary">
                                        {msg("linked_to_stash", "Linked to Stash")}
                                      </Badge>
                                    ) : (
                                      <Button
                                        type="button"
                                        variant="outline"
                                        disabled={busy || loading}
                                        onClick={() => {
                                          setSelected({ identity });
                                          setNotice(null);
                                        }}
                                      >
                                        {msg("manage_binding", "Link Stash performer")}
                                      </Button>
                                    )}
                                  </CardFooter>
                                </Card>
                              ))}
                          </TabsContent>
                          {rows.length > 12 && (
                            <nav
                              className="catalog-review-line"
                              aria-label={msg("pagination", "Catalog review pages")}
                            >
                              <Button
                                type="button"
                                variant="outline"
                                disabled={busy || currentPage === 0}
                                onClick={() => setPage(currentPage - 1)}
                              >
                                {msg("previous", "Previous")}
                              </Button>
                              <span>
                                {msg("page", "Page {page} of {pages}", {
                                  page: currentPage + 1,
                                  pages: Math.ceil(rows.length / 12),
                                })}
                              </span>
                              <Button
                                type="button"
                                variant="outline"
                                disabled={busy || (currentPage + 1) * 12 >= rows.length}
                                onClick={() => setPage(currentPage + 1)}
                              >
                                {msg("next", "Next")}
                              </Button>
                            </nav>
                          )}
                        </section>
                      );
                    }}
                  </form.Subscribe>
                  {selected && (
                    <ReviewPanel
                      key={selected.row?.account_key ?? selected.identity.id}
                      row={selected.row}
                      identity={selected.identity}
                      identities={data.identities}
                      performers={data.performers}
                      onBusy={setBusy}
                      onApplied={applied}
                      onClose={() => setSelected(null)}
                    />
                  )}
                </div>
              </Tabs>
            </>
          )}
        </div>
      </div>
    );
  }
  host.routes.add({ path: "/catalogMetadata/review", component: ReviewPage });
  host.nav.add({
    to: "/catalogMetadata/review",
    label: (intl) =>
      intl.formatMessage({
        id: "catalogMetadata.review.title",
        defaultMessage: "Catalog review",
      }),
    placement: "utility",
  });
}
