---
name: bootstrap-5
description: Build modern, responsive, accessible web interfaces using pure Bootstrap 5. Use when creating layouts, components, forms, or styling with Bootstrap's utility classes and components. Covers grid system, flexbox utilities, spacing, colors, typography, forms, buttons, cards, modals, navbars, dropdowns, alerts, and best practices for responsive design.
license: MIT
metadata:
  author: bootstrap-community
  version: "5.3"
  bootstrap_version: "5.3.x"
---

# Bootstrap 5 Professional Usage Guide

## Quick Start

Include Bootstrap via CDN:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Bootstrap 5</title>
    <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
      rel="stylesheet"
    />
  </head>
  <body>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
```

## Responsive Breakpoints

| Breakpoint  | Class Infix | Dimensions |
| ----------- | ----------- | ---------- |
| Extra small | (none)      | <576px     |
| Small       | `sm`        | >=576px    |
| Medium      | `md`        | >=768px    |
| Large       | `lg`        | >=992px    |
| Extra large | `xl`        | >=1200px   |
| XXL         | `xxl`       | >=1400px   |

## Layout System

### Containers

```html
<div class="container">Fixed-width responsive container</div>
<div class="container-fluid">Full-width container</div>
<div class="container-md">100% until md breakpoint</div>
```

### Grid System (12-column flexbox)

```html
<div class="container">
  <div class="row">
    <div class="col">Auto-width column</div>
    <div class="col-6">6-column width</div>
    <div class="col-md-4">4 columns on md+</div>
  </div>
  <div class="row row-cols-1 row-cols-md-3 g-4">
    <div class="col">Column 1</div>
    <div class="col">Column 2</div>
  </div>
</div>
```

### Gutters (Spacing between columns)

```html
<div class="row g-0">No gutters</div>
<div class="row g-3">1rem gutters</div>
<div class="row gx-5">Horizontal gutters only</div>
<div class="row gy-3">Vertical gutters only</div>
```

## Spacing Utilities

Format: `{property}{sides}-{size}` or `{property}{sides}-{breakpoint}-{size}`

- Property: `m` (margin), `p` (padding)
- Sides: `t` (top), `b` (bottom), `s` (start/left in LTR), `e` (end/right in LTR), `x` (horizontal), `y` (vertical), blank (all)
- Sizes: `0`, `1` (.25rem), `2` (.5rem), `3` (1rem), `4` (1.5rem), `5` (3rem), `auto`

```html
<div class="m-3 p-2">Margin 1rem, padding .5rem</div>
<div class="mt-0 pt-5">No top margin, 3rem top padding</div>
<div class="mx-auto">Horizontally centered</div>
<div class="mb-md-5">3rem bottom margin on md+</div>
```

## Flexbox Utilities

```html
<div class="d-flex">Flex container</div>
<div class="d-inline-flex">Inline flex</div>
<div class="d-md-flex">Flex on md+</div>

<div class="d-flex flex-row">Horizontal (default)</div>
<div class="d-flex flex-column">Vertical</div>
<div class="d-flex flex-column-reverse">Vertical reversed</div>

<div class="d-flex justify-content-start">Align left</div>
<div class="d-flex justify-content-center">Center</div>
<div class="d-flex justify-content-end">Right</div>
<div class="d-flex justify-content-between">Space between</div>
<div class="d-flex justify-content-around">Space around</div>
<div class="d-flex justify-content-evenly">Even spacing</div>

<div class="d-flex align-items-start">Top</div>
<div class="d-flex align-items-center">Center</div>
<div class="d-flex align-items-end">Bottom</div>
<div class="d-flex align-items-stretch">Stretch (default)</div>

<div class="d-flex flex-wrap">Allow wrapping</div>
<div class="d-flex flex-nowrap">No wrapping</div>

<div class="d-flex flex-fill">Fill available space</div>
<div class="flex-grow-1">Grow to fill</div>
<div class="flex-shrink-0">Don't shrink</div>

<div class="order-first">First in order</div>
<div class="order-last">Last in order</div>
<div class="order-0 through order-5">Order by number</div>
```

## Colors & Backgrounds

### Theme Colors

- `primary` (blue), `secondary` (gray), `success` (green), `danger` (red), `warning` (yellow), `info` (cyan), `light`, `dark`

### Text Colors

```html
<p class="text-primary">Primary text</p>
<p class="text-danger">Danger text</p>
<p class="text-body-secondary">Muted text</p>
<p class="text-white bg-dark">White on dark</p>
```

### Background Colors

```html
<div class="bg-primary text-white">Primary background</div>
<div class="bg-light">Light background</div>
<div class="bg-gradient bg-primary">With gradient</div>
<div class="bg-opacity-75">75% opacity</div>
```

### Combined Text + Background

```html
<div class="text-bg-primary">Auto contrasting colors</div>
<div class="text-bg-danger">Danger with white text</div>
```

## Typography

```html
<h1 class="h1">Heading 1</h1>
<h1 class="display-1">Display heading (larger)</h1>
<p class="lead">Lead paragraph (emphasized)</p>
<p class="small">Smaller text</p>
<p class="fw-bold">Bold text</p>
<p class="fw-light">Light weight</p>
<p class="fst-italic">Italic</p>
<p class="text-decoration-none">No underline</p>
<p class="text-start">Left aligned</p>
<p class="text-center">Centered</p>
<p class="text-end">Right aligned</p>
<p class="text-truncate">Truncated with ellipsis...</p>
<p class="text-wrap">Normal wrapping</p>
<p class="text-nowrap">No wrapping</p>
```

## Display & Visibility

```html
<div class="d-none">Hidden on all</div>
<div class="d-block">Block display</div>
<div class="d-inline">Inline display</div>
<div class="d-inline-block">Inline-block</div>
<div class="d-none d-md-block">Hidden until md, then block</div>
<div class="d-md-none">Visible only below md</div>
<div class="visible">Visibility: visible</div>
<div class="invisible">Visibility: hidden (keeps space)</div>
```

## Sizing

```html
<div class="w-25">25% width</div>
<div class="w-50">50% width</div>
<div class="w-75">75% width</div>
<div class="w-100">100% width</div>
<div class="w-auto">Auto width</div>
<div class="mw-100">Max-width: 100%</div>
<div class="vh-100">100% viewport height</div>
<div class="h-100">100% height</div>
```

## Position

```html
<div class="position-static">Static</div>
<div class="position-relative">Relative</div>
<div class="position-absolute">Absolute</div>
<div class="position-fixed">Fixed</div>
<div class="position-sticky">Sticky</div>
<div class="fixed-top">Fixed to top</div>
<div class="fixed-bottom">Fixed to bottom</div>
<div class="sticky-top">Sticky top</div>
<div class="top-0 start-0">Top-left corner</div>
<div class="bottom-0 end-0">Bottom-right corner</div>
<div class="translate-middle">Center with transform</div>
```

## Borders & Shadows

```html
<div class="border">All borders</div>
<div class="border-top">Top border only</div>
<div class="border-0">No borders</div>
<div class="border border-primary">Primary color border</div>
<div class="border-0 border-top border-primary">Compound utilities</div>
<div class="rounded">Rounded corners</div>
<div class="rounded-circle">Circle (equal sides)</div>
<div class="rounded-pill">Pill shape</div>
<div class="rounded-0">No rounding</div>
<div class="shadow-sm">Small shadow</div>
<div class="shadow">Regular shadow</div>
<div class="shadow-lg">Large shadow</div>
<div class="shadow-none">No shadow</div>
```

## Buttons

```html
<button class="btn">Base button</button>
<button class="btn btn-primary">Primary</button>
<button class="btn btn-outline-primary">Outline</button>
<button class="btn btn-lg">Large</button>
<button class="btn btn-sm">Small</button>
<button class="btn btn-primary" disabled>Disabled</button>
<a class="btn btn-primary" href="#" role="button">Link button</a>
```

### Button Groups

```html
<div class="btn-group">
  <button class="btn btn-primary">Left</button>
  <button class="btn btn-primary">Middle</button>
  <button class="btn btn-primary">Right</button>
</div>
```

### Block Buttons

```html
<div class="d-grid gap-2">
  <button class="btn btn-primary">Block button</button>
</div>
<div class="d-grid gap-2 d-md-flex justify-content-md-end">
  <button class="btn btn-primary">Responsive block</button>
</div>
```

## Cards

```html
<div class="card" style="width: 18rem;">
  <img src="..." class="card-img-top" alt="..." />
  <div class="card-body">
    <h5 class="card-title">Card title</h5>
    <p class="card-text">Content here.</p>
    <a href="#" class="btn btn-primary">Action</a>
  </div>
</div>

<div class="card text-bg-dark">
  <img src="..." class="card-img" alt="..." />
  <div class="card-img-overlay">
    <h5 class="card-title">Overlay</h5>
  </div>
</div>
```

### Card Grid Layout

```html
<div class="row row-cols-1 row-cols-md-3 g-4">
  <div class="col">
    <div class="card h-100">Equal height card</div>
  </div>
</div>
```

## Navigation

### Navbar

```html
<nav class="navbar navbar-expand-lg bg-body-tertiary">
  <div class="container-fluid">
    <a class="navbar-brand" href="#">Brand</a>
    <button
      class="navbar-toggler"
      type="button"
      data-bs-toggle="collapse"
      data-bs-target="#navbarNav"
    >
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        <li class="nav-item">
          <a class="nav-link active" aria-current="page" href="#">Home</a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="#">Link</a>
        </li>
        <li class="nav-item dropdown">
          <a
            class="nav-link dropdown-toggle"
            href="#"
            role="button"
            data-bs-toggle="dropdown"
            >Dropdown</a
          >
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="#">Action</a></li>
            <li><hr class="dropdown-divider" /></li>
            <li><a class="dropdown-item" href="#">Another</a></li>
          </ul>
        </li>
      </ul>
      <form class="d-flex" role="search">
        <input class="form-control me-2" type="search" placeholder="Search" />
        <button class="btn btn-outline-success" type="submit">Search</button>
      </form>
    </div>
  </div>
</nav>
```

### Tabs & Pills

```html
<ul class="nav nav-tabs">
  <li class="nav-item"><a class="nav-link active" href="#">Active</a></li>
  <li class="nav-item"><a class="nav-link" href="#">Link</a></li>
</ul>

<ul class="nav nav-pills">
  <li class="nav-item"><a class="nav-link active" href="#">Active</a></li>
</ul>
```

## Dropdowns (Requires Popper.js - included in bundle)

```html
<div class="dropdown">
  <button
    class="btn btn-secondary dropdown-toggle"
    type="button"
    data-bs-toggle="dropdown"
  >
    Dropdown
  </button>
  <ul class="dropdown-menu">
    <li><a class="dropdown-item" href="#">Action</a></li>
    <li><a class="dropdown-item" href="#">Another</a></li>
    <li><hr class="dropdown-divider" /></li>
    <li><a class="dropdown-item" href="#">Separated</a></li>
  </ul>
</div>
```

## Modal

```html
<button
  type="button"
  class="btn btn-primary"
  data-bs-toggle="modal"
  data-bs-target="#exampleModal"
>
  Launch modal
</button>

<div
  class="modal fade"
  id="exampleModal"
  tabindex="-1"
  aria-labelledby="exampleModalLabel"
  aria-hidden="true"
>
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h1 class="modal-title fs-5" id="exampleModalLabel">Modal title</h1>
        <button
          type="button"
          class="btn-close"
          data-bs-dismiss="modal"
          aria-label="Close"
        ></button>
      </div>
      <div class="modal-body">Modal body content</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
          Close
        </button>
        <button type="button" class="btn btn-primary">Save</button>
      </div>
    </div>
  </div>
</div>
```

## Alerts

```html
<div class="alert alert-primary" role="alert">Primary alert</div>
<div class="alert alert-danger" role="alert">Danger alert</div>
<div class="alert alert-success alert-dismissible fade show" role="alert">
  <strong>Success!</strong> Dismissible alert.
  <button
    type="button"
    class="btn-close"
    data-bs-dismiss="alert"
    aria-label="Close"
  ></button>
</div>
```

## Forms

### Basic Form

```html
<form>
  <div class="mb-3">
    <label for="email" class="form-label">Email</label>
    <input
      type="email"
      class="form-control"
      id="email"
      aria-describedby="emailHelp"
    />
    <div id="emailHelp" class="form-text">We'll never share your email.</div>
  </div>
  <div class="mb-3">
    <label for="password" class="form-label">Password</label>
    <input type="password" class="form-control" id="password" />
  </div>
  <div class="mb-3 form-check">
    <input type="checkbox" class="form-check-input" id="check1" />
    <label class="form-check-label" for="check1">Check me</label>
  </div>
  <button type="submit" class="btn btn-primary">Submit</button>
</form>
```

### Form Controls

```html
<input class="form-control" type="text" placeholder="Text input" />
<input class="form-control form-control-lg" type="text" placeholder="Large" />
<input class="form-control form-control-sm" type="text" placeholder="Small" />
<textarea class="form-control" rows="3"></textarea>
<select class="form-select">
  <option selected>Open this select</option>
  <option value="1">One</option>
</select>
```

### Checkboxes & Radios

```html
<div class="form-check">
  <input class="form-check-input" type="checkbox" id="flexCheckDefault" />
  <label class="form-check-label" for="flexCheckDefault">Checkbox</label>
</div>
<div class="form-check">
  <input
    class="form-check-input"
    type="radio"
    name="flexRadioDefault"
    id="radio1"
  />
  <label class="form-check-label" for="radio1">Radio</label>
</div>
<div class="form-check form-switch">
  <input class="form-check-input" type="checkbox" id="flexSwitchCheck" />
  <label class="form-check-label" for="flexSwitchCheck">Switch</label>
</div>
```

### Floating Labels

```html
<div class="form-floating mb-3">
  <input
    type="email"
    class="form-control"
    id="floatingInput"
    placeholder="Email"
  />
  <label for="floatingInput">Email address</label>
</div>
```

### Input Groups

```html
<div class="input-group mb-3">
  <span class="input-group-text">@</span>
  <input type="text" class="form-control" placeholder="Username" />
</div>
<div class="input-group mb-3">
  <input type="text" class="form-control" placeholder="Recipient's username" />
  <span class="input-group-text">@example.com</span>
</div>
```

### Form Validation

```html
<form class="needs-validation" novalidate>
  <div class="mb-3">
    <label for="validation01" class="form-label">First name</label>
    <input type="text" class="form-control" id="validation01" required />
    <div class="valid-feedback">Looks good!</div>
    <div class="invalid-feedback">Please provide a valid name.</div>
  </div>
  <button class="btn btn-primary" type="submit">Submit</button>
</form>
```

### Form Grid Layout

```html
<form class="row g-3">
  <div class="col-md-6">
    <label for="inputEmail4" class="form-label">Email</label>
    <input type="email" class="form-control" id="inputEmail4" />
  </div>
  <div class="col-md-6">
    <label for="inputPassword4" class="form-label">Password</label>
    <input type="password" class="form-control" id="inputPassword4" />
  </div>
  <div class="col-12">
    <button type="submit" class="btn btn-primary">Sign in</button>
  </div>
</form>
```

## Other Components

### Badge

```html
<span class="badge bg-primary">Primary</span>
<span class="badge rounded-pill bg-secondary">Pill badge</span>
<button class="btn btn-primary">
  Notifications <span class="badge text-bg-secondary">4</span>
</button>
```

### Breadcrumb

```html
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    <li class="breadcrumb-item"><a href="#">Home</a></li>
    <li class="breadcrumb-item"><a href="#">Library</a></li>
    <li class="breadcrumb-item active" aria-current="page">Data</li>
  </ol>
</nav>
```

### Pagination

```html
<nav aria-label="Page navigation">
  <ul class="pagination">
    <li class="page-item"><a class="page-link" href="#">Previous</a></li>
    <li class="page-item"><a class="page-link" href="#">1</a></li>
    <li class="page-item active"><a class="page-link" href="#">2</a></li>
    <li class="page-item"><a class="page-link" href="#">3</a></li>
    <li class="page-item"><a class="page-link" href="#">Next</a></li>
  </ul>
</nav>
```

### Progress

```html
<div class="progress">
  <div
    class="progress-bar"
    role="progressbar"
    style="width: 25%"
    aria-valuenow="25"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    25%
  </div>
</div>
<div class="progress">
  <div class="progress-bar bg-success" style="width: 75%"></div>
</div>
```

### Spinner

```html
<div class="spinner-border text-primary" role="status">
  <span class="visually-hidden">Loading...</span>
</div>
<div class="spinner-grow text-primary" role="status">
  <span class="visually-hidden">Loading...</span>
</div>
```

### Accordion

```html
<div class="accordion" id="accordionExample">
  <div class="accordion-item">
    <h2 class="accordion-header">
      <button
        class="accordion-button"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#collapseOne"
      >
        Accordion Item #1
      </button>
    </h2>
    <div
      id="collapseOne"
      class="accordion-collapse collapse show"
      data-bs-parent="#accordionExample"
    >
      <div class="accordion-body">Content here.</div>
    </div>
  </div>
</div>
```

### List Group

```html
<ul class="list-group">
  <li class="list-group-item">An item</li>
  <li class="list-group-item active">Active item</li>
  <li class="list-group-item disabled" aria-disabled="true">Disabled</li>
</ul>
<div class="list-group">
  <a href="#" class="list-group-item list-group-item-action active"
    >Active link</a
  >
</div>
```

### Offcanvas (Slide-out panel)

```html
<button
  class="btn btn-primary"
  type="button"
  data-bs-toggle="offcanvas"
  data-bs-target="#offcanvasExample"
>
  Open offcanvas
</button>
<div class="offcanvas offcanvas-start" tabindex="-1" id="offcanvasExample">
  <div class="offcanvas-header">
    <h5 class="offcanvas-title">Offcanvas</h5>
    <button
      type="button"
      class="btn-close"
      data-bs-dismiss="offcanvas"
    ></button>
  </div>
  <div class="offcanvas-body">Content here.</div>
</div>
```

### Toast

```html
<button type="button" class="btn btn-primary" id="liveToastBtn">
  Show toast
</button>
<div class="toast-container position-fixed bottom-0 end-0 p-3">
  <div
    id="liveToast"
    class="toast"
    role="alert"
    aria-live="assertive"
    aria-atomic="true"
  >
    <div class="toast-header">
      <strong class="me-auto">Bootstrap</strong>
      <small>11 mins ago</small>
      <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
    </div>
    <div class="toast-body">Hello, world! This is a toast message.</div>
  </div>
</div>
```

## Accessibility Best Practices

### Always Include

- `role="button"` on `<a>` elements used as buttons
- `aria-label` for icon-only buttons
- `aria-current="page"` for active navigation items
- `aria-describedby` linking inputs to their help text
- `aria-expanded` and `aria-controls` for collapsibles
- Proper heading hierarchy (h1 -> h2 -> h3)
- `.visually-hidden` for screen-reader-only text

### Color Contrast

- Ensure 4.5:1 contrast ratio for text
- Don't rely solely on color to convey meaning
- Test with accessibility tools

### Focus Management

- Visible focus states (Bootstrap provides these)
- Logical tab order
- Skip links for main content

## Common Patterns

### Centered Content

```html
<div class="d-flex justify-content-center align-items-center vh-100">
  <div>Centered content</div>
</div>
```

### Responsive Image

```html
<img src="..." class="img-fluid" alt="..." />
<img src="..." class="img-thumbnail" alt="..." />
```

### Equal Height Columns

```html
<div class="row">
  <div class="col-md-6">
    <div class="card h-100">Equal height</div>
  </div>
  <div class="col-md-6">
    <div class="card h-100">Equal height</div>
  </div>
</div>
```

### Sticky Footer

```html
<body class="d-flex flex-column min-vh-100">
  <main class="flex-grow-1">Content</main>
  <footer>Footer</footer>
</body>
```

### Responsive Visibility

```html
<div class="d-none d-md-block">Hidden on mobile, visible md+</div>
<div class="d-md-none">Visible only on mobile</div>
<div class="d-none d-lg-block">Visible only lg+</div>
```

## JavaScript API (for dynamic control)

```js
const modal = new bootstrap.Modal("#myModal");
modal.show();
modal.hide();

const dropdown = new bootstrap.Dropdown("#myDropdown");
dropdown.toggle();

const toast = new bootstrap.Toast("#myToast");
toast.show();

const collapse = new bootstrap.Collapse("#myCollapse");
collapse.toggle();
```

## Key Principles

1. **Mobile First**: Write CSS for smallest screens, then add breakpoint modifiers
2. **Use Semantic HTML**: `<nav>`, `<main>`, `<article>`, `<section>`, `<aside>`
3. **Combine Utilities**: Stack multiple utility classes for complex styles
4. **Don't Override**: Use Bootstrap's utilities before writing custom CSS
5. **Test Responsiveness**: Check all breakpoints during development
