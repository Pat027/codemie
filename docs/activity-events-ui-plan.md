# Activity Events Admin Page — Frontend Implementation Plan

## Goal

Add a read-only "Activity events" page under Settings → Administration, visible to maintainers only. Shows the audit log from `GET /v1/admin/activity-events` with filters, pagination, and actor enrichment.

## Files

| Action | Path |
|---|---|
| Create | `src/types/entity/activityEvent.ts` |
| Create | `src/store/activityEvents.ts` |
| Create | `src/pages/settings/administration/ActivityEventsPage.tsx` |
| Modify | `src/constants/index.ts` |
| Modify | `src/pages/settings/tabs.tsx` |
| Modify | `src/router.tsx` |

---

## Task 1 — Types

**Create** `src/types/entity/activityEvent.ts`:

```typescript
// Copyright 2026 EPAM Systems, Inc. ("EPAM")
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

export interface ActivityEvent {
  id: string
  domain: string
  event_type: string
  entity_type: string | null
  entity_id: string | null
  actor_id: string | null
  actor_email: string | null
  actor_name: string | null
  attributes: Record<string, unknown> | null
  created_at: string
}

export interface ActivityEventFilterOptions {
  domains: string[]
  event_types: string[]
  entity_types: string[]
}

export interface ActivityEventListParams {
  limit?: number
  offset?: number
  domain?: string | null
  event_type?: string | null
  entity_type?: string | null
  entity_id?: string | null
  actor_id?: string | null
  from?: string | null
  to?: string | null
  sort_dir?: 'asc' | 'desc'
}
```

---

## Task 2 — Store

**Create** `src/store/activityEvents.ts`:

```typescript
// Copyright 2026 EPAM Systems, Inc. ("EPAM")
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

import { proxy } from 'valtio'

import { Pagination, PaginatedResponse } from '@/types/common'
import { ActivityEvent, ActivityEventFilterOptions, ActivityEventListParams } from '@/types/entity/activityEvent'
import api from '@/utils/api'
import toaster from '@/utils/toaster'

const DEFAULT_LIMIT = 50

interface ActivityEventsStore {
  events: ActivityEvent[]
  pagination: Pagination
  loading: boolean
  filterOptions: ActivityEventFilterOptions | null
  filterOptionsLoading: boolean
  listEvents: (params?: ActivityEventListParams) => Promise<void>
  loadFilterOptions: () => Promise<void>
}

export const activityEventsStore = proxy<ActivityEventsStore>({
  events: [],
  pagination: {
    page: 0,
    perPage: DEFAULT_LIMIT,
    totalPages: 0,
    totalCount: 0,
  },
  loading: false,
  filterOptions: null,
  filterOptionsLoading: false,

  async listEvents(params: ActivityEventListParams = {}) {
    this.loading = true
    try {
      const limit = params.limit ?? DEFAULT_LIMIT
      const offset = params.offset ?? 0

      const queryParams: Record<string, string> = {
        limit: String(limit),
        offset: String(offset),
      }
      if (params.domain) queryParams.domain = params.domain
      if (params.event_type) queryParams.event_type = params.event_type
      if (params.entity_type) queryParams.entity_type = params.entity_type
      if (params.entity_id) queryParams.entity_id = params.entity_id
      if (params.actor_id) queryParams.actor_id = params.actor_id
      if (params.from) queryParams.from = params.from
      if (params.to) queryParams.to = params.to
      if (params.sort_dir) queryParams.sort_dir = params.sort_dir

      const response = await api.get('v1/admin/activity-events', {
        params: queryParams,
        skipErrorHandling: true,
      })
      const data = (await response.json()) as PaginatedResponse<ActivityEvent>

      this.events = data.data ?? []
      const total = data.pagination?.total ?? 0
      const perPage = data.pagination?.per_page ?? limit
      this.pagination = {
        page: data.pagination?.page ?? 0,
        perPage,
        totalPages: Math.ceil(total / perPage),
        totalCount: total,
      }
    } catch (error: any) {
      const msg = error?.parsedError?.message ?? error?.message ?? 'Failed to load activity events'
      toaster.error(msg)
      throw error
    } finally {
      this.loading = false
    }
  },

  async loadFilterOptions() {
    if (this.filterOptions) return
    this.filterOptionsLoading = true
    try {
      const response = await api.get('v1/admin/activity-events/filter-options', {
        skipErrorHandling: true,
      })
      this.filterOptions = (await response.json()) as ActivityEventFilterOptions
    } catch (error: any) {
      const msg = error?.parsedError?.message ?? error?.message ?? 'Failed to load filter options'
      toaster.error(msg)
    } finally {
      this.filterOptionsLoading = false
    }
  },
})
```

---

## Task 3 — Page Component

**Create** `src/pages/settings/administration/ActivityEventsPage.tsx`:

```typescript
// Copyright 2026 EPAM Systems, Inc. ("EPAM")
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

import { FC, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useSnapshot } from 'valtio'

import Select from '@/components/form/Select/Select'
import Input from '@/components/form/Input/Input'
import DatePicker from '@/components/form/DatePicker/DatePicker'
import Table from '@/components/Table'
import { DECIMAL_PAGINATION_OPTIONS } from '@/constants'
import SettingsLayout from '@/pages/settings/components/SettingsLayout'
import { activityEventsStore } from '@/store/activityEvents'
import { userStore } from '@/store/user'
import { ActivityEvent } from '@/types/entity/activityEvent'
import { ColumnDefinition, DefinitionTypes } from '@/types/table'
import { formatDateTime } from '@/utils/helpers'
import { displayValue } from '@/utils/utils'
import toaster from '@/utils/toaster'

const columnDefinitions: ColumnDefinition[] = [
  { key: 'created_at', label: 'When', type: DefinitionTypes.Custom, headClassNames: 'w-[14%]' },
  { key: 'domain', label: 'Domain', type: DefinitionTypes.String, headClassNames: 'w-[12%]' },
  { key: 'event_type', label: 'Event', type: DefinitionTypes.String, headClassNames: 'w-[18%]' },
  { key: 'entity', label: 'Entity', type: DefinitionTypes.Custom, headClassNames: 'w-[18%]' },
  { key: 'actor', label: 'Actor', type: DefinitionTypes.Custom, headClassNames: 'w-[16%]' },
  { key: 'attributes', label: 'Details', type: DefinitionTypes.Custom, headClassNames: 'w-[22%]' },
]

const SORT_OPTIONS = [
  { label: 'Newest first', value: 'desc' },
  { label: 'Oldest first', value: 'asc' },
]

const ActivityEventsPage: FC = () => {
  const navigate = useNavigate()
  const { user: currentUser } = useSnapshot(userStore)
  const { events, pagination, loading, filterOptions } = useSnapshot(activityEventsStore)
  const isMaintainer = currentUser?.isMaintainer ?? false

  const [domain, setDomain] = useState<string>('')
  const [eventType, setEventType] = useState<string>('')
  const [entityType, setEntityType] = useState<string>('')
  const [entityId, setEntityId] = useState<string>('')
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [perPage, setPerPage] = useState(50)

  useEffect(() => {
    if (currentUser && !isMaintainer) {
      toaster.error('Access denied. This page is for maintainers only.')
      navigate('/settings/administration')
    }
  }, [isMaintainer, currentUser, navigate])

  useEffect(() => {
    if (!isMaintainer) return
    activityEventsStore.loadFilterOptions()
  }, [isMaintainer])

  const loadEvents = useCallback(
    (page = 0, limit = perPage) => {
      activityEventsStore
        .listEvents({
          limit,
          offset: page * limit,
          domain: domain || null,
          event_type: eventType || null,
          entity_type: entityType || null,
          entity_id: entityId || null,
          from: from || null,
          to: to || null,
          sort_dir: sortDir,
        })
        .catch((error) => console.error('Failed to load activity events:', error))
    },
    [domain, eventType, entityType, entityId, from, to, sortDir, perPage]
  )

  useEffect(() => {
    if (!isMaintainer) return
    loadEvents(0, perPage)
  }, [isMaintainer, domain, eventType, entityType, entityId, from, to, sortDir, loadEvents, perPage])

  const domainOptions = useMemo(
    () => [{ label: 'All domains', value: '' }, ...(filterOptions?.domains ?? []).map((d) => ({ label: d, value: d }))],
    [filterOptions]
  )

  const eventTypeOptions = useMemo(
    () => [
      { label: 'All events', value: '' },
      ...(filterOptions?.event_types ?? []).map((e) => ({ label: e, value: e })),
    ],
    [filterOptions]
  )

  const entityTypeOptions = useMemo(
    () => [
      { label: 'All entity types', value: '' },
      ...(filterOptions?.entity_types ?? []).map((t) => ({ label: t, value: t })),
    ],
    [filterOptions]
  )

  const customRenderColumns = useMemo(
    () => ({
      created_at: (item: ActivityEvent) => (
        <span className="whitespace-nowrap text-text-primary text-sm">
          {formatDateTime(item.created_at)}
        </span>
      ),
      entity: (item: ActivityEvent) => (
        <div className="flex flex-col min-w-0">
          {item.entity_type && (
            <span className="text-xs text-text-quaternary truncate">{item.entity_type}</span>
          )}
          {item.entity_id && (
            <span className="text-text-primary text-sm truncate" title={item.entity_id}>
              {item.entity_id}
            </span>
          )}
          {!item.entity_type && !item.entity_id && (
            <span className="text-text-quaternary">—</span>
          )}
        </div>
      ),
      actor: (item: ActivityEvent) => (
        <div className="flex flex-col min-w-0">
          {item.actor_name && (
            <span className="text-text-primary text-sm truncate">{item.actor_name}</span>
          )}
          {item.actor_email && (
            <span className="text-xs text-text-quaternary truncate">{item.actor_email}</span>
          )}
          {!item.actor_name && !item.actor_email && (
            <span className="text-text-quaternary">system</span>
          )}
        </div>
      ),
      attributes: (item: ActivityEvent) => {
        if (!item.attributes) return <span className="text-text-quaternary">—</span>
        const text = JSON.stringify(item.attributes)
        const truncated = text.length > 120 ? text.slice(0, 120) + '…' : text
        return (
          <span
            className="text-text-primary text-xs font-mono break-all"
            title={text}
          >
            {truncated}
          </span>
        )
      },
    }),
    []
  )

  if (currentUser && !isMaintainer) return null

  const content = (
    <div className="flex flex-col h-full pt-4">
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="w-44">
          <Select
            label="Domain"
            value={domain}
            options={domainOptions}
            onChangeValue={(v) => { setDomain(v || ''); }}
          />
        </div>
        <div className="w-52">
          <Select
            label="Event type"
            value={eventType}
            options={eventTypeOptions}
            onChangeValue={(v) => { setEventType(v || ''); }}
          />
        </div>
        <div className="w-44">
          <Select
            label="Entity type"
            value={entityType}
            options={entityTypeOptions}
            onChangeValue={(v) => { setEntityType(v || ''); }}
          />
        </div>
        <div className="w-52">
          <Input
            label="Entity ID"
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            placeholder="Filter by entity ID"
          />
        </div>
        <div className="w-44">
          <DatePicker
            label="From"
            value={from}
            onChange={setFrom}
            showTime
            hourFormat="24"
          />
        </div>
        <div className="w-44">
          <DatePicker
            label="To"
            value={to}
            onChange={setTo}
            showTime
            hourFormat="24"
          />
        </div>
        <div className="w-40">
          <Select
            label="Sort"
            value={sortDir}
            options={SORT_OPTIONS}
            onChangeValue={(v) => setSortDir((v || 'desc') as 'asc' | 'desc')}
          />
        </div>
      </div>

      <Table
        items={events as ActivityEvent[]}
        columnDefinitions={columnDefinitions}
        customRenderColumns={customRenderColumns}
        loading={loading}
        pagination={{
          page: pagination.page,
          totalPages: pagination.totalPages,
          perPage: pagination.perPage,
        }}
        onPaginationChange={(page, newPerPage) => {
          const limit = newPerPage ?? perPage
          setPerPage(limit)
          loadEvents(page, limit)
        }}
        perPageOptions={DECIMAL_PAGINATION_OPTIONS}
      />
    </div>
  )

  return (
    <SettingsLayout
      contentTitle="Activity events"
      content={content}
    />
  )
}

export default ActivityEventsPage
```

---

## Task 4 — Register the tab enum value

**Modify** `src/constants/index.ts` — add one line to `SettingsTab`:

Find:
```typescript
export enum SettingsTab {
  PROFILE = 'profile',
  ADMINISTRATION = 'administration',
  BUDGETS_MANAGEMENT = 'budgets_management',
```

Add after `BUDGETS_MANAGEMENT`:
```typescript
  ACTIVITY_EVENTS = 'activity_events',
```

---

## Task 5 — Add sidebar nav item

**Modify** `src/pages/settings/tabs.tsx`.

After the `budgetsManagementTab` block (lines 81–91), add:

```typescript
  const activityEventsTab: LayoutTab[] = isMaintainer
    ? [
        {
          id: SettingsTab.ACTIVITY_EVENTS,
          name: 'Activity events',
          title: 'Activity events',
          url: '/settings/administration/activity-events',
        },
      ]
    : []
```

Then add `...activityEventsTab` to `administrationChildren`. The `administrationChildren` array is sorted alphabetically (`.sort((a, b) => a.name.localeCompare(b.name))`), so the item appears in the right position automatically.

In the `isAdmin` branch, the array currently starts with:
```typescript
const administrationChildren = isAdmin
  ? [
      ...(isCostCentersFeatureEnabled ? [...] : []),
      {
        id: SettingsTab.PROJECTS_MANAGEMENT,
        ...
      },
      ...(isEnterprise
        ? getEnterpriseAdminItems(...)
        : []),
    ].sort(...)
  : [
      {
        id: SettingsTab.PROJECTS_MANAGEMENT,
        ...
      },
    ]
```

Add `...activityEventsTab` in **both** branches (admin and non-admin) before the `.sort()` call in the admin branch, and as a spread in the non-admin array:

```typescript
const administrationChildren = isAdmin
  ? [
      ...activityEventsTab,                          // ← add here
      ...(isCostCentersFeatureEnabled ? [...] : []),
      {
        id: SettingsTab.PROJECTS_MANAGEMENT,
        ...
      },
      ...(isEnterprise
        ? getEnterpriseAdminItems(...)
        : []),
    ].sort((a, b) => a.name.localeCompare(b.name))
  : [
      ...activityEventsTab,                          // ← and here
      {
        id: SettingsTab.PROJECTS_MANAGEMENT,
        ...
      },
    ]
```

---

## Task 6 — Register the route

**Modify** `src/router.tsx`.

**Add the import** near the other administration page imports (alphabetical order, around line 60–72):
```typescript
import ActivityEventsPage from '@/pages/settings/administration/ActivityEventsPage'
```

**Add the route** inside `settingsRoutes` after the `budgets-management` entry (around line 464):
```typescript
  {
    id: 'activity-events',
    path: '/settings/administration/activity-events',
    Component: ActivityEventsPage,
  },
```

---

## Verification checklist

- [ ] Log in as a maintainer → Settings → Administration → "Activity events" appears in the sidebar
- [ ] Page loads and shows the event table with data
- [ ] Selecting a domain filter reloads the table and resets to page 0
- [ ] Selecting an event type filter works independently from domain
- [ ] Setting `from` / `to` date filters the results by time range
- [ ] Pagination works: changing page and per-page both work
- [ ] `actor_name` / `actor_email` show in the Actor column; events with no actor show "system"
- [ ] `attributes` column shows truncated JSON with full JSON on hover (title attribute)
- [ ] Log in as a non-maintainer admin → navigating to `/settings/administration/activity-events` redirects back to `/settings/administration`
- [ ] Log in as a regular user → "Activity events" does not appear in the sidebar
