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
  } = host.ui;
  const { Link } = host.router;
  const msg = (id, defaultMessage, values) =>
    host.intl.formatMessage({ id: `catalogMetadata.review.${id}`, defaultMessage }, values);
  const personLabel = (p) =>
    `${p.name}${p.disambiguation ? ` (${p.disambiguation})` : ""} · #${p.id}`;
  const errorMessage = (error) => (error instanceof Error ? error.message : String(error));
  const statusLabel = (status) =>
    ({
      attention: msg("attention", "Needs review"),
      conflict: msg("conflict", "Conflicting links"),
      candidate: msg("candidate", "Name or alias match"),
      proposed: msg("proposed", "Ready to review"),
      linked: msg("linked", "Linked"),
      unmatched: msg("unmatched", "No match"),
      all: msg("all", "All catalogs"),
    })[status];

  function Account({ account, performers }) {
    return (
      <div className="catalog-review-account">
        <div className="catalog-review-line">
          <Badge variant="secondary">{account.platform}</Badge>
          <strong>{account.handles.join(", ") || account.source_id}</strong>
        </div>
        <code>{account.account_key}</code>
        {account.evidence?.length > 0 && (
          <ul className="catalog-review-evidence">
            {account.evidence.map((item, index) => {
              const p = performers.find((person) => person.id === item.performer_id);
              const kind = {
                explicit_link: msg("explicit", "Explicit account link"),
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
                    <span>{msg("reused", "This handle appears on multiple account IDs.")}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    );
  }

  function ReviewPanel({ row, performers, onClose, onApplied, onBusy }) {
    const initial =
      row.status === "conflict"
        ? null
        : (performers.find((p) => p.id === row.performer_id) ?? null);
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
          performer: z
            .object({ id: z.string().min(1) })
            .nullable()
            .refine(Boolean, msg("choose", "Choose a performer.")),
        }),
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
            performer_id: value.performer.id,
          });
          if (alive.current) setPreview(next);
        } catch (error) {
          if (alive.current) setError(errorMessage(error));
        } finally {
          if (alive.current) {
            setPending(null);
            onBusy(false);
          }
        }
      },
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
    const needle = search.trim().toLocaleLowerCase();
    const options = [...performers]
      .sort(
        (a, b) =>
          Number(row.candidate_ids.includes(b.id)) - Number(row.candidate_ids.includes(a.id)),
      )
      .filter(
        (p) =>
          !needle ||
          [p.id, p.name, p.disambiguation, ...p.alias_list, ...p.urls].some((value) =>
            value?.toLocaleLowerCase().includes(needle),
          ),
      )
      .slice(0, 40);
    return (
      <Card
        className="catalog-review-detail"
        ref={panel}
        tabIndex={-1}
        aria-labelledby="catalog-review-title"
      >
        <CardHeader>
          <CardTitle id="catalog-review-title">
            {msg("review_catalog", "Review {label}", { label: row.label })}
          </CardTitle>
          <CardDescription>
            {msg(
              "whole_catalog",
              "Choose the performer who owns every account below. Accounts already joined in one creator catalog stay together.",
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="catalog-review-stack">
          <code>{row.catalog_id}</code>
          {row.conflicts.map((conflict, i) => (
            <Alert key={i} variant="destructive">
              <AlertTitle>{msg("conflict", "Conflicting links")}</AlertTitle>
              <AlertDescription>{conflict.reason}</AlertDescription>
            </Alert>
          ))}
          {row.accounts.map((account) => (
            <Account key={account.account_key} account={account} performers={performers} />
          ))}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              event.stopPropagation();
              void form.handleSubmit();
            }}
          >
            <FieldGroup>
              <form.Field name="performer">
                {(field) => {
                  const invalid = field.state.meta.isTouched && !field.state.meta.isValid;
                  return (
                    <Field data-invalid={invalid}>
                      <FieldLabel htmlFor="catalog-review-performer">
                        {msg("performer", "Stash performer")}
                      </FieldLabel>
                      <Combobox
                        items={options}
                        filter={null}
                        value={field.state.value}
                        disabled={!!pending}
                        onValueChange={(value) => {
                          field.handleChange(value);
                          setPreview(null);
                          setError(null);
                        }}
                        itemToStringLabel={personLabel}
                        itemToStringValue={(p) => p.id}
                        isItemEqualToValue={(a, b) => a.id === b.id}
                        onOpenChange={(open) => {
                          if (open) setSearch("");
                        }}
                        onInputValueChange={(value, details) => {
                          if (["input-change", "input-clear"].includes(details.reason))
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
                                  <strong>{personLabel(p)}</strong>
                                  {p.alias_list.length > 0 && (
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
                        {msg(
                          "suggested_first",
                          "Candidates appear first. Names and aliases can collide; check the performer ID, disambiguation and profile evidence.",
                        )}
                      </FieldDescription>
                      {invalid && <FieldError errors={field.state.meta.errors} />}
                    </Field>
                  );
                }}
              </form.Field>
              <Button type="submit" variant="outline" disabled={!!pending}>
                {pending === "preview" && <Spinner />}
                {msg("preview", "Preview link")}
              </Button>
            </FieldGroup>
          </form>
          {error && (
            <Alert variant="destructive" role="alert">
              <AlertTitle>{msg("failed", "Could not complete the request")}</AlertTitle>
              <AlertDescription>
                {error}
                <p>
                  {msg(
                    "retry_preview",
                    "Preview again to retry with current data. A failed apply may have saved the explicit choice; catalog copies can be retried.",
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
                {msg("link_to", "Link to {performer}", {
                  performer: personLabel(preview.performer),
                })}
              </h3>
              <p>
                {msg(
                  "preview_explanation",
                  "Save the selected accounts as explicit links. All catalogs below will share this performer identity and use the performer’s name as their label.",
                )}
              </p>
              {preview.catalogs.map((catalog) => (
                <div className="catalog-review-preview-catalog" key={catalog.id}>
                  <div className="catalog-review-line">
                    <strong>{catalog.label}</strong>
                    <Badge variant="outline">
                      {catalog.id === preview.target_catalog
                        ? msg("destination", "Destination")
                        : msg("merge_into", "Merge into destination")}
                    </Badge>
                  </div>
                  <code>{catalog.id}</code>
                  <ul>
                    {catalog.accounts.map((account) => (
                      <li key={account.account_key}>
                        {account.platform}: {account.handles.join(", ")}{" "}
                        <code>{account.account_key}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              <p>
                {msg(
                  "preserved",
                  "Source account IDs, posts and captured evidence are preserved. Media files stay in place. This does not merge Stash performers or re-import existing scenes and images.",
                )}
              </p>
              {preview.other_conflicts.length > 0 && (
                <Alert>
                  <AlertTitle>{msg("other_conflicts", "Other conflicts remain")}</AlertTitle>
                  <AlertDescription>
                    {msg(
                      "other_conflicts_detail",
                      "Only the catalogs shown above will be linked. Other conflicting catalogs remain for review.",
                    )}
                  </AlertDescription>
                </Alert>
              )}
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
                {msg("apply", "Apply reviewed link")}
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
      } catch (error) {
        if (request.current === id) setError(errorMessage(error));
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
          { accounts: result.linked_accounts, catalogs: result.merged_catalogs },
        ),
      );
      setSelected(null);
      void refresh();
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
                  "subtitle",
                  "Resolve creator account links and performer conflicts. Browsing and previewing do not change Stash or the catalogs.",
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
              {msg("scope", "Scene and image mapping previews remain in plugin settings.")}
            </span>
          </div>
          {notice && (
            <Alert role="status">
              <AlertTitle>{msg("saved_title", "Link applied")}</AlertTitle>
              <AlertDescription>{notice}</AlertDescription>
            </Alert>
          )}
          {error && (
            <Alert variant="destructive" role="alert">
              <AlertTitle>{msg("load_failed", "Could not load catalog reviews")}</AlertTitle>
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
                        <code>{conflict.account_key}</code> · #{conflict.performer_id}:{" "}
                        {conflict.reason}
                      </p>
                    ))}
                    <p>
                      {msg(
                        "missing_links_settings",
                        "Check Performer account links in plugin settings for these entries.",
                      )}
                    </p>
                  </AlertDescription>
                </Alert>
              )}
              <FieldGroup className="catalog-review-filters">
                <form.Field name="search">
                  {(field) => (
                    <Field>
                      <FieldLabel htmlFor="catalog-review-search">
                        {msg("search", "Search catalogs")}
                      </FieldLabel>
                      <Input
                        id="catalog-review-search"
                        value={field.state.value}
                        disabled={busy}
                        placeholder={msg(
                          "search_hint",
                          "Handle, account key, catalog or performer",
                        )}
                        onChange={(event) => {
                          field.handleChange(event.target.value);
                          setPage(0);
                        }}
                      />
                    </Field>
                  )}
                </form.Field>
                <form.Field name="status">
                  {(field) => (
                    <Field>
                      <FieldLabel htmlFor="catalog-review-status">{msg("show", "Show")}</FieldLabel>
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
                              "unmatched",
                              "all",
                            ].map((value) => (
                              <SelectItem key={value} value={value}>
                                {statusLabel(value)}
                                {value in data.counts ? ` (${data.counts[value]})` : ""}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                    </Field>
                  )}
                </form.Field>
              </FieldGroup>
              <div
                className={`catalog-review-layout${selected ? " has-selection" : ""}`}
                aria-busy={loading || busy}
              >
                <form.Subscribe selector={(state) => state.values}>
                  {(filters) => {
                    const needle = filters.search.trim().toLocaleLowerCase();
                    const people = Object.fromEntries(data.performers.map((p) => [p.id, p]));
                    const rows = data.catalogs.filter(
                      (row) =>
                        (filters.status === "all" ||
                          filters.status === row.status ||
                          (filters.status === "attention" &&
                            ["conflict", "candidate", "proposed"].includes(row.status))) &&
                        (!needle ||
                          [
                            row.label,
                            row.catalog_id,
                            ...row.accounts.flatMap((a) => [a.account_key, ...a.handles]),
                            ...row.candidate_ids.flatMap((id) => [
                              id,
                              people[id]?.name,
                              people[id]?.disambiguation,
                              ...(people[id]?.alias_list ?? []),
                            ]),
                          ].some((value) => value?.toLocaleLowerCase().includes(needle))),
                    );
                    const currentPage = Math.min(
                      page,
                      Math.max(0, Math.ceil(rows.length / 12) - 1),
                    );
                    return (
                      <section
                        className="catalog-review-stack"
                        aria-label={msg("catalogs", "Creator catalogs")}
                      >
                        <p role="status">
                          {msg("count", "{count, number} catalogs", { count: rows.length })}
                        </p>
                        {rows.length === 0 && (
                          <p>
                            {msg(
                              "empty",
                              "No catalogs match these filters. Try All catalogs or another search.",
                            )}
                          </p>
                        )}
                        {rows.slice(currentPage * 12, (currentPage + 1) * 12).map((row) => (
                          <Card key={row.catalog_id}>
                            <CardHeader>
                              <div className="catalog-review-line">
                                <CardTitle>{row.label}</CardTitle>
                                <Badge
                                  variant={row.status === "conflict" ? "destructive" : "secondary"}
                                >
                                  {statusLabel(row.status)}
                                </Badge>
                              </div>
                              <CardDescription>
                                {row.accounts
                                  .map(
                                    (a) => `${a.platform}: ${a.handles.join(", ") || a.source_id}`,
                                  )
                                  .join(" · ")}
                              </CardDescription>
                            </CardHeader>
                            <CardContent>
                              <code>{row.catalog_id}</code>
                              {row.candidate_ids.length > 0 && (
                                <p>
                                  {msg("candidates", "Candidates: {names}", {
                                    names: row.candidate_ids
                                      .map((id) =>
                                        people[id] ? personLabel(people[id]) : `#${id}`,
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
                                  busy || loading || selected?.catalog_id === row.catalog_id
                                }
                                onClick={() => {
                                  setSelected(row);
                                  setNotice(null);
                                }}
                                aria-label={msg("review_catalog", "Review {label}", {
                                  label: row.label,
                                })}
                              >
                                {msg("review", "Review")}
                              </Button>
                            </CardFooter>
                          </Card>
                        ))}
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
                    key={selected.catalog_id}
                    row={selected}
                    performers={data.performers}
                    onBusy={setBusy}
                    onApplied={applied}
                    onClose={() => setSelected(null)}
                  />
                )}
              </div>
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
      intl.formatMessage({ id: "catalogMetadata.review.title", defaultMessage: "Catalog review" }),
    placement: "utility",
  });
}
