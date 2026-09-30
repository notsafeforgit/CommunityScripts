import React from "react";
import { createRoot } from "react-dom/client";
import { IntlProvider, createIntl } from "react-intl";
import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { ApolloClient, ApolloLink, InMemoryCache, Observable } from "@apollo/client";
import { ApolloProvider } from "@apollo/client/react";
import { registerPlugin } from "../src/plugins/loader";
import { getRegisteredRoutes } from "../src/plugins/registry";
import "../tests/browser/fixture/style.css";
import register from "__CATALOG_ENTRY__";

const people = [
  {
    id: "1",
    name: "Sam",
    disambiguation: "First person",
    alias_list: ["account"],
    urls: ["https://x.com/account"],
  },
  {
    id: "2",
    name: "Sam",
    disambiguation: "Second person",
    alias_list: ["account", "elsewhere"],
    urls: ["https://reddit.com/user/elsewhere"],
  },
];
const cidA = "c_11111111111111111111111111111111";
const cidB = "c_22222222222222222222222222222222";
const uuid = "7c8c6ed6-a995-4f73-86ba-5db62af7d1e2";
const accounts = [
  {
    account_key: "twitter:id:10",
    platform: "twitter",
    source_id: "10",
    identity_basis: "source-id",
    handles: ["account"],
    catalog_id: cidA,
    catalog_label: "account, twitter",
    directories: ["account, twitter"],
    profile_urls: [],
    label: "account",
    identity_id: null,
    identity_name: null,
    performer_id: null,
    candidate_ids: ["1", "2"],
    status: "conflict",
    conflicts: [{ reason: "Multiple performers match this account." }],
    evidence: [
      { kind: "profile_url", performer_id: "1", url: "https://x.com/account" },
      { kind: "name_only", performer_id: "2" },
    ],
  },
  {
    account_key: "reddit:id:t2_20",
    platform: "reddit",
    source_id: "t2_20",
    identity_basis: "source-id",
    handles: ["elsewhere"],
    catalog_id: cidB,
    catalog_label: "elsewhere, reddit",
    directories: ["elsewhere, reddit"],
    profile_urls: [],
    label: "elsewhere",
    identity_id: uuid,
    identity_name: "Sam",
    performer_id: "2",
    candidate_ids: ["2"],
    status: "linked",
    conflicts: [],
    evidence: [],
  },
];
const params = new URLSearchParams(location.search);
if (params.has("many")) {
  for (let i = 0; i < 25; i++) accounts.push({
    ...structuredClone(accounts[0]), account_key: `twitter:id:extra${i}`,
    label: `account extra ${i}`, handles: [`account extra ${i}`],
  });
}
const bindingState = params.get("binding");
let stashBindings = bindingState === "none" ? [] : [
  {
    namespace: bindingState === "other-library" ? "other-library" : "stash",
    performer_id: bindingState === "missing" ? "99" : bindingState === "redirect" ? "1" : "2",
    name: "Sam",
    redirect_to: bindingState === "redirect" ? "2" : null,
    available: !bindingState,
  },
];
const blocked = params.has("dry")
  ? "Dry run is enabled. Turn it off in Catalog Metadata settings to apply links."
  : null;
let failList = params.has("fail-list");
let failApply = !bindingState;
const requests = [];
window.reviewRequests = requests;
function catalogPerformer() {
  return {
    id: uuid,
    name: "Sam",
    alias_list: ["account", "elsewhere"],
    urls: [],
    accounts: accounts.filter((a) => a.identity_id === uuid),
    merged_ids: [],
    stash_bindings: stashBindings,
  };
}
const client = new ApolloClient({
  cache: new InMemoryCache(),
  link: new ApolloLink(
    (operation) =>
      new Observable((observer) => {
        requests.push({
          name: operation.operationName,
          ...operation.variables,
        });
        const input = operation.variables.input ?? {};
        const action = input.action ?? "link";
        if (operation.variables.operation === "list_reviews") {
          if (failList) {
            failList = false;
            observer.error(new Error("Catalog temporarily unavailable"));
            return;
          }
          observer.next({
            data: {
              pluginQueryV3: {
                performers: people,
                identities: [catalogPerformer()],
                accounts,
                namespace: "stash",
                blocked_reason: blocked,
                unattached_conflicts: [],
                counts: Object.fromEntries(
                  ["conflict", "linked", "unlinked"].map((status) => [
                    status,
                    accounts.filter((a) => a.status === status).length,
                  ]),
                ),
              },
            },
          });
        } else if (operation.variables.operation === "review_link") {
          const account = accounts.find((a) => a.account_key === input.account_key);
          observer.next({
            data: {
              pluginQueryV3: {
                review_token: "r".repeat(64),
                action,
                choice: input,
                account,
                performer: people.find((p) => p.id === input.performer_id) ?? null,
                identity_id: action === "unlink" ? null : uuid,
                identity_name: action === "unlink" ? null : "Sam",
                creates_identity: false,
                previous_identity_id: account?.identity_id,
                previous_identity_name: account?.identity_name,
                associated_accounts: accounts.filter(
                  (a) => a.identity_id === uuid && a !== account,
                ),
                blocked_reason: blocked,
              },
            },
          });
        } else if (operation.variables.operation === "apply_link") {
          if (failApply) {
            failApply = false;
            observer.error(
              new Error("The review is out of date. Preview again before applying."),
            );
            return;
          }
          const account = accounts.find((a) => a.account_key === input.account_key);
          if (action === "bind") {
            stashBindings = [
              ...stashBindings.filter((binding) => binding.namespace !== "stash" || binding.performer_id !== input.performer_id),
              {
                namespace: "stash",
                performer_id: input.performer_id,
                name: people.find((person) => person.id === input.performer_id).name,
                redirect_to: null,
                available: true,
              },
            ];
          }
          if (account)
            Object.assign(account, {
              identity_id: action === "unlink" ? null : uuid,
              identity_name: action === "unlink" ? null : "Sam",
              status: action === "unlink" ? "unlinked" : "linked",
              conflicts: [],
              performer_id: action === "unlink" ? null : "2",
            });
          observer.next({
            data: {
              pluginMutationV3: {
                action,
                identity_id: action === "unlink" ? null : uuid,
                account_key: account?.account_key,
                performer_id: "2",
                linked_accounts: action === "link" ? 1 : 0,
                updates: {
                  accounts: (account ? [account] : accounts.filter((item) => item.identity_id === uuid)).map((item) => ({
                    ...item,
                    reviewed: true,
                    binding_conflicts: [],
                    candidate_ids: item.performer_id ? [item.performer_id] : [],
                  })),
                  identities: [catalogPerformer()],
                  performers: people.filter((person) => person.id === "2"),
                  performer_ids: ["2"],
                  namespace: "stash",
                  blocked_reason: blocked,
                },
              },
            },
          });
        } else {
          observer.error(new Error("Unexpected operation"));
          return;
        }
        observer.complete();
      }),
  ),
});
await registerPlugin(
  { id: "catalogMetadata", name: "Catalog Metadata", entry: "fixture" },
  {
    apollo: client,
    intl: createIntl({ locale: "en-GB", defaultLocale: "en-GB" }),
  },
  5000,
  async () => ({ default: register }),
);
const root = createRootRoute({
  component: () => (
    <div
      style={{
        height: "100dvh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <Outlet />
    </div>
  ),
});
const router = createRouter({
  basepath: "/stash",
  routeTree: root.addChildren([
    ...getRegisteredRoutes().map((route) =>
      createRoute({
        getParentRoute: () => root,
        path: route.path,
        component: route.component,
      }),
    ),
    createRoute({
      getParentRoute: () => root,
      path: "/settings/plugins",
      component: () => <p>Plugin settings</p>,
    }),
  ]),
});
createRoot(document.getElementById("root")).render(
  <IntlProvider locale="en-GB" defaultLocale="en-GB">
    <ApolloProvider client={client}>
      <RouterProvider router={router} />
    </ApolloProvider>
  </IntlProvider>,
);
