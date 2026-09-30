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
const accounts = [
  {
    account_key: "twitter:id:10",
    platform: "twitter",
    source_id: "10",
    handles: ["account"],
    catalog_id: cidA,
    evidence: [
      { kind: "profile_url", performer_id: "1", url: "https://x.com/account" },
      { kind: "name_only", performer_id: "2" },
    ],
  },
  {
    account_key: "reddit:id:t2_20",
    platform: "reddit",
    source_id: "t2_20",
    handles: ["elsewhere"],
    catalog_id: cidB,
    evidence: [],
  },
];
const params = new URLSearchParams(location.search);
const blocked = params.has("dry")
  ? "Dry run is enabled. Turn it off in Catalog Metadata settings to apply links."
  : null;
let failList = params.has("fail-list");
let failApply = true;
const requests = [];
window.reviewRequests = requests;
const client = new ApolloClient({
  cache: new InMemoryCache(),
  link: new ApolloLink(
    (operation) =>
      new Observable((observer) => {
        requests.push({ name: operation.operationName, ...operation.variables });
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
                blocked_reason: blocked,
                unattached_conflicts: [],
                counts: { conflict: 1, proposed: 1 },
                catalogs: [
                  {
                    catalog_id: cidA,
                    label: "account",
                    status: "conflict",
                    accounts: [accounts[0]],
                    candidate_ids: ["1", "2"],
                    performer_id: null,
                    conflicts: [{ reason: "Multiple performers match this account." }],
                  },
                  {
                    catalog_id: cidB,
                    label: "elsewhere",
                    status: "proposed",
                    accounts: [accounts[1]],
                    candidate_ids: ["2"],
                    performer_id: "2",
                    conflicts: [],
                  },
                ],
              },
            },
          });
        } else if (operation.variables.operation === "review_link") {
          observer.next({
            data: {
              pluginQueryV3: {
                review_token: "r".repeat(64),
                catalog_id: cidA,
                performer: people.find((p) => p.id === operation.variables.input.performer_id),
                catalogs: [
                  { id: cidA, label: "account", accounts: [accounts[0]] },
                  { id: cidB, label: "elsewhere", accounts: [accounts[1]] },
                ],
                target_catalog: cidA,
                explicit_links: { "twitter:id:10": operation.variables.input.performer_id },
                blocked_reason: blocked,
                other_conflicts: [],
              },
            },
          });
        } else if (operation.variables.operation === "apply_link") {
          if (failApply) {
            failApply = false;
            observer.error(new Error("The review is out of date. Preview again before applying."));
            return;
          }
          observer.next({
            data: {
              pluginMutationV3: {
                linked_accounts: 2,
                merged_catalogs: 1,
                catalog_id: cidA,
                performer_id: "2",
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
  { apollo: client, intl: createIntl({ locale: "en-GB", defaultLocale: "en-GB" }) },
  5000,
  async () => ({ default: register }),
);
const root = createRootRoute({
  component: () => (
    <div style={{ height: "100dvh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Outlet />
    </div>
  ),
});
const router = createRouter({
  basepath: "/stash",
  routeTree: root.addChildren([
    ...getRegisteredRoutes().map((route) =>
      createRoute({ getParentRoute: () => root, path: route.path, component: route.component }),
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
