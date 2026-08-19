# Bootstrap 5 Component Reference

## Complete Component List

### Layout Components

- Containers: `.container`, `.container-fluid`, `.container-{breakpoint}`
- Grid: `.row`, `.col`, `.col-{1-12}`, `.col-{breakpoint}-{1-12}`
- CSS Grid: `.grid`, `.gap-{0-5}`, `g-col-{1-12}`

### Content Components

- Typography: `.h1-h6`, `.display-1-6`, `.lead`, `.small`
- Images: `.img-fluid`, `.img-thumbnail`, `.figure`
- Tables: `.table`, `.table-striped`, `.table-hover`, `.table-responsive`
- Figures: `.figure`, `.figure-img`, `.figure-caption`

### Form Components

- Control: `.form-control`, `.form-control-lg/sm`, `.form-select`
- Check/Radio: `.form-check`, `.form-check-input`, `.form-check-label`
- Switch: `.form-switch`
- Range: `.form-range`
- Floating: `.form-floating`
- Input Group: `.input-group`, `.input-group-text`
- Validation: `.was-validated`, `.is-valid/invalid`, `.valid/invalid-feedback/tooltip`

### Component Classes

#### Accordion

```html
<div class="accordion" id="accordionExample">
  <div class="accordion-item">
    <h2 class="accordion-header">
      <button
        class="accordion-button"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#collapseOne"
        aria-expanded="true"
        aria-controls="collapseOne"
      >
        Item #1
      </button>
    </h2>
    <div
      id="collapseOne"
      class="accordion-collapse collapse show"
      data-bs-parent="#accordionExample"
    >
      <div class="accordion-body">Body content</div>
    </div>
  </div>
  <div class="accordion-item">
    <h2 class="accordion-header">
      <button
        class="accordion-button collapsed"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#collapseTwo"
        aria-expanded="false"
        aria-controls="collapseTwo"
      >
        Item #2
      </button>
    </h2>
    <div
      id="collapseTwo"
      class="accordion-collapse collapse"
      data-bs-parent="#accordionExample"
    >
      <div class="accordion-body">Body content</div>
    </div>
  </div>
</div>
```

#### Alerts

```html
<div class="alert alert-primary" role="alert">Primary alert</div>
<div class="alert alert-secondary" role="alert">Secondary alert</div>
<div class="alert alert-success" role="alert">Success alert</div>
<div class="alert alert-danger" role="alert">Danger alert</div>
<div class="alert alert-warning" role="alert">Warning alert</div>
<div class="alert alert-info" role="alert">Info alert</div>
<div class="alert alert-light" role="alert">Light alert</div>
<div class="alert alert-dark" role="alert">Dark alert</div>

<div class="alert alert-primary d-flex align-items-center" role="alert">
  <svg class="bi flex-shrink-0 me-2" role="img" aria-label="Info:">...</svg>
  <div>Alert with icon</div>
</div>

<div class="alert alert-success alert-dismissible fade show" role="alert">
  <h4 class="alert-heading">Well done!</h4>
  <p>Content here.</p>
  <hr />
  <p class="mb-0">Additional info.</p>
  <button
    type="button"
    class="btn-close"
    data-bs-dismiss="alert"
    aria-label="Close"
  ></button>
</div>
```

#### Badge

```html
<span class="badge text-bg-primary">Primary</span>
<span class="badge text-bg-secondary">Secondary</span>
<span class="badge text-bg-success">Success</span>
<span class="badge text-bg-danger">Danger</span>
<span class="badge text-bg-warning">Warning</span>
<span class="badge text-bg-info">Info</span>
<span class="badge text-bg-light">Light</span>
<span class="badge text-bg-dark">Dark</span>

<span class="badge rounded-pill text-bg-primary">Pill badge</span>
<span class="badge rounded-circle bg-danger p-2">9</span>
```

#### Breadcrumb

```html
<nav style="--bs-breadcrumb-divider: '>';" aria-label="breadcrumb">
  <ol class="breadcrumb">
    <li class="breadcrumb-item"><a href="#">Home</a></li>
    <li class="breadcrumb-item"><a href="#">Library</a></li>
    <li class="breadcrumb-item active" aria-current="page">Data</li>
  </ol>
</nav>
```

#### Buttons

```html
<button type="button" class="btn btn-primary">Primary</button>
<button type="button" class="btn btn-secondary">Secondary</button>
<button type="button" class="btn btn-success">Success</button>
<button type="button" class="btn btn-danger">Danger</button>
<button type="button" class="btn btn-warning">Warning</button>
<button type="button" class="btn btn-info">Info</button>
<button type="button" class="btn btn-light">Light</button>
<button type="button" class="btn btn-dark">Dark</button>
<button type="button" class="btn btn-link">Link</button>

<button type="button" class="btn btn-outline-primary">Outline</button>
<button type="button" class="btn btn-outline-secondary">
  Outline Secondary
</button>

<button type="button" class="btn btn-primary btn-lg">Large</button>
<button type="button" class="btn btn-primary btn-sm">Small</button>

<button type="button" class="btn btn-primary" disabled>Disabled</button>
<a class="btn btn-primary disabled" role="button" aria-disabled="true"
  >Disabled Link</a
>

<button type="button" class="btn btn-primary" data-bs-toggle="button">
  Toggle
</button>
```

#### Button Group

```html
<div class="btn-group" role="group" aria-label="Basic example">
  <button type="button" class="btn btn-primary">Left</button>
  <button type="button" class="btn btn-primary">Middle</button>
  <button type="button" class="btn btn-primary">Right</button>
</div>

<div class="btn-toolbar" role="toolbar" aria-label="Toolbar">
  <div class="btn-group me-2" role="group">...</div>
  <div class="btn-group me-2" role="group">...</div>
</div>

<div class="btn-group-vertical">
  <button type="button" class="btn btn-primary">Top</button>
  <button type="button" class="btn btn-primary">Middle</button>
  <button type="button" class="btn btn-primary">Bottom</button>
</div>
```

#### Card

```html
<div class="card">
  <div class="card-header">Header</div>
  <img src="..." class="card-img-top" alt="..." />
  <div class="card-body">
    <h5 class="card-title">Title</h5>
    <h6 class="card-subtitle mb-2 text-body-secondary">Subtitle</h6>
    <p class="card-text">Text content.</p>
    <a href="#" class="card-link">Link</a>
    <a href="#" class="btn btn-primary">Button</a>
  </div>
  <ul class="list-group list-group-flush">
    <li class="list-group-item">Item</li>
  </ul>
  <div class="card-footer text-body-secondary">Footer</div>
</div>

<div class="card text-bg-primary">Colored card</div>
<div class="card border-primary">Bordered card</div>
<div class="card-group">Card group</div>
<div class="row row-cols-1 row-cols-md-3 g-4">Card grid</div>
```

#### Carousel

```html
<div id="carouselExample" class="carousel slide" data-bs-ride="carousel">
  <div class="carousel-indicators">
    <button
      type="button"
      data-bs-target="#carouselExample"
      data-bs-slide-to="0"
      class="active"
      aria-current="true"
    ></button>
    <button
      type="button"
      data-bs-target="#carouselExample"
      data-bs-slide-to="1"
    ></button>
  </div>
  <div class="carousel-inner">
    <div class="carousel-item active">
      <img src="..." class="d-block w-100" alt="..." />
      <div class="carousel-caption d-none d-md-block">
        <h5>Caption</h5>
        <p>Description</p>
      </div>
    </div>
    <div class="carousel-item">
      <img src="..." class="d-block w-100" alt="..." />
    </div>
  </div>
  <button
    class="carousel-control-prev"
    type="button"
    data-bs-target="#carouselExample"
    data-bs-slide="prev"
  >
    <span class="carousel-control-prev-icon" aria-hidden="true"></span>
    <span class="visually-hidden">Previous</span>
  </button>
  <button
    class="carousel-control-next"
    type="button"
    data-bs-target="#carouselExample"
    data-bs-slide="next"
  >
    <span class="carousel-control-next-icon" aria-hidden="true"></span>
    <span class="visually-hidden">Next</span>
  </button>
</div>
```

#### Close Button

```html
<button type="button" class="btn-close" aria-label="Close"></button>
<button type="button" class="btn-close" disabled aria-label="Close"></button>
<button
  type="button"
  class="btn-close btn-close-white"
  aria-label="Close"
></button>
```

#### Collapse

```html
<p>
  <button
    class="btn btn-primary"
    type="button"
    data-bs-toggle="collapse"
    data-bs-target="#collapseExample"
    aria-expanded="false"
    aria-controls="collapseExample"
  >
    Toggle
  </button>
</p>
<div class="collapse" id="collapseExample">
  <div class="card card-body">Content here.</div>
</div>

<p>
  <button
    class="btn btn-primary"
    type="button"
    data-bs-toggle="collapse"
    data-bs-target="#multiCollapseExample1"
  >
    Toggle first
  </button>
  <button
    class="btn btn-primary"
    type="button"
    data-bs-toggle="collapse"
    data-bs-target="#multiCollapseExample2"
  >
    Toggle second
  </button>
</p>
<div class="row">
  <div class="col">
    <div class="collapse multi-collapse" id="multiCollapseExample1">First</div>
  </div>
  <div class="col">
    <div class="collapse multi-collapse" id="multiCollapseExample2">Second</div>
  </div>
</div>

<div id="accordion">
  <div class="accordion-item">
    <h2 class="accordion-header">
      <button
        class="accordion-button collapsed"
        data-bs-toggle="collapse"
        data-bs-target="#collapseOne"
      >
        Accordion
      </button>
    </h2>
    <div
      id="collapseOne"
      class="accordion-collapse collapse"
      data-bs-parent="#accordion"
    >
      <div class="accordion-body">Body</div>
    </div>
  </div>
</div>
```

#### Dropdown

```html
<div class="dropdown">
  <button
    class="btn btn-secondary dropdown-toggle"
    type="button"
    data-bs-toggle="dropdown"
    aria-expanded="false"
  >
    Dropdown button
  </button>
  <ul class="dropdown-menu">
    <li><a class="dropdown-item" href="#">Action</a></li>
    <li><a class="dropdown-item" href="#">Another action</a></li>
    <li><hr class="dropdown-divider" /></li>
    <li><a class="dropdown-item" href="#">Something else</a></li>
  </ul>
</div>

<div class="btn-group dropup">
  <button>...</button>
  <ul class="dropdown-menu">
    ...
  </ul>
</div>
<div class="btn-group dropend">
  <button>...</button>
  <ul class="dropdown-menu">
    ...
  </ul>
</div>
<div class="btn-group dropstart">
  <button>...</button>
  <ul class="dropdown-menu">
    ...
  </ul>
</div>

<ul class="dropdown-menu dropdown-menu-dark">
  Dark menu
</ul>
<ul class="dropdown-menu dropdown-menu-end">
  Right-aligned
</ul>
<ul class="dropdown-menu">
  <li><h6 class="dropdown-header">Header</h6></li>
  <li><span class="dropdown-item-text">Text</span></li>
  <li><a class="dropdown-item active" href="#">Active</a></li>
  <li><a class="dropdown-item disabled">Disabled</a></li>
</ul>

<div class="dropdown-menu p-4">
  <form>Form content</form>
</div>
```

#### List Group

```html
<ul class="list-group">
  <li class="list-group-item">Item</li>
  <li class="list-group-item active">Active</li>
  <li class="list-group-item disabled" aria-disabled="true">Disabled</li>
  <li class="list-group-item list-group-item-primary">Primary</li>
  <li class="list-group-item list-group-item-action">Actionable</li>
</ul>

<div class="list-group">
  <a
    href="#"
    class="list-group-item list-group-item-action active"
    aria-current="true"
  >
    <div class="d-flex w-100 justify-content-between">
      <h5 class="mb-1">Heading</h5>
      <small>3 days ago</small>
    </div>
    <p class="mb-1">Content.</p>
    <small>Footer text.</small>
  </a>
</div>

<ul class="list-group list-group-horizontal">
  <li class="list-group-item">Horizontal</li>
</ul>

<ul class="list-group list-group-numbered">
  <li class="list-group-item">Numbered</li>
</ul>

<ul class="list-group list-group-checkable">
  <input
    class="list-group-item-check"
    type="radio"
    name="listGroupCheckableRadios"
    id="listGroupCheckableRadios1"
  />
  <label class="list-group-item" for="listGroupCheckableRadios1"
    >Checkable</label
  >
</ul>
```

#### Modal

```html
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
        <h1 class="modal-title fs-5" id="exampleModalLabel">Title</h1>
        <button
          type="button"
          class="btn-close"
          data-bs-dismiss="modal"
          aria-label="Close"
        ></button>
      </div>
      <div class="modal-body">Body</div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
          Close
        </button>
        <button type="button" class="btn btn-primary">Save</button>
      </div>
    </div>
  </div>
</div>

<div class="modal-dialog modal-dialog-scrollable">Scrollable body</div>
<div class="modal-dialog modal-dialog-centered">Centered vertically</div>
<div class="modal-dialog modal-sm">Small</div>
<div class="modal-dialog modal-lg">Large</div>
<div class="modal-dialog modal-xl">Extra large</div>
<div class="modal-dialog modal-fullscreen">Fullscreen</div>
<div class="modal-dialog modal-fullscreen-sm-down">Fullscreen below sm</div>

<div class="modal" data-bs-backdrop="static" data-bs-keyboard="false">
  Static backdrop
</div>
```

#### Navbar

```html
<nav class="navbar navbar-expand-lg bg-body-tertiary">
  <div class="container-fluid">
    <a class="navbar-brand" href="#">Brand</a>
    <button
      class="navbar-toggler"
      type="button"
      data-bs-toggle="collapse"
      data-bs-target="#navbarNav"
      aria-controls="navbarNav"
      aria-expanded="false"
      aria-label="Toggle navigation"
    >
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        <li class="nav-item">
          <a class="nav-link active" aria-current="page" href="#">Home</a>
        </li>
        <li class="nav-item"><a class="nav-link" href="#">Features</a></li>
        <li class="nav-item">
          <a class="nav-link disabled" aria-disabled="true">Disabled</a>
        </li>
      </ul>
      <form class="d-flex" role="search">
        <input class="form-control me-2" type="search" placeholder="Search" />
        <button class="btn btn-outline-success" type="submit">Search</button>
      </form>
    </div>
  </div>
</nav>

<nav class="navbar bg-body-tertiary fixed-top">Fixed top</nav>
<nav class="navbar bg-body-tertiary fixed-bottom">Fixed bottom</nav>
<nav class="navbar bg-body-tertiary sticky-top">Sticky top</nav>

<nav class="navbar bg-primary" data-bs-theme="dark">Dark theme</nav>
```

#### Navs & Tabs

```html
<ul class="nav">
  <li class="nav-item"><a class="nav-link active" href="#">Active</a></li>
  <li class="nav-item"><a class="nav-link" href="#">Link</a></li>
  <li class="nav-item">
    <a class="nav-link disabled" aria-disabled="true">Disabled</a>
  </li>
</ul>

<ul class="nav nav-tabs">
  <li class="nav-item"><a class="nav-link active" href="#">Active</a></li>
</ul>

<ul class="nav nav-pills">
  <li class="nav-item"><a class="nav-link active" href="#">Active</a></li>
</ul>

<ul class="nav nav-pills nav-fill">
  ...
</ul>
<ul class="nav nav-pills nav-justified">
  ...
</ul>
<nav class="nav nav-tabs flex-column flex-sm-row">Responsive nav</nav>

<div data-bs-toggle="tab">Tab toggle</div>
```

#### Offcanvas

```html
<button
  class="btn btn-primary"
  type="button"
  data-bs-toggle="offcanvas"
  data-bs-target="#offcanvasExample"
>
  Launch
</button>

<div
  class="offcanvas offcanvas-start"
  tabindex="-1"
  id="offcanvasExample"
  aria-labelledby="offcanvasExampleLabel"
>
  <div class="offcanvas-header">
    <h5 class="offcanvas-title" id="offcanvasExampleLabel">Offcanvas</h5>
    <button
      type="button"
      class="btn-close"
      data-bs-dismiss="offcanvas"
      aria-label="Close"
    ></button>
  </div>
  <div class="offcanvas-body">Body content</div>
</div>

<div class="offcanvas offcanvas-top">Top</div>
<div class="offcanvas offcanvas-bottom">Bottom</div>
<div class="offcanvas offcanvas-start">Left</div>
<div class="offcanvas offcanvas-end">Right</div>

<div
  class="offcanvas offcanvas-start"
  data-bs-scroll="true"
  data-bs-backdrop="false"
>
  No backdrop
</div>
```

#### Pagination

```html
<nav aria-label="Page navigation example">
  <ul class="pagination">
    <li class="page-item"><a class="page-link" href="#">Previous</a></li>
    <li class="page-item"><a class="page-link" href="#">1</a></li>
    <li class="page-item active"><a class="page-link" href="#">2</a></li>
    <li class="page-item"><a class="page-link" href="#">3</a></li>
    <li class="page-item"><a class="page-link" href="#">Next</a></li>
  </ul>
</nav>

<ul class="pagination pagination-lg">
  Large
</ul>
<ul class="pagination pagination-sm">
  Small
</ul>
<ul class="pagination justify-content-center">
  Centered
</ul>
```

#### Placeholder

```html
<p aria-hidden="true">
  <span class="placeholder col-6"></span>
  <span class="placeholder w-75"></span>
  <span class="placeholder" style="width: 25%;"></span>
</p>

<span class="placeholder col-12 placeholder-lg">Large</span>
<span class="placeholder col-12 placeholder-sm">Small</span>
<span class="placeholder col-12 placeholder-xs">Extra small</span>

<p class="placeholder-glow">
  <span class="placeholder col-12"></span>
</p>
<p class="placeholder-wave">
  <span class="placeholder col-12"></span>
</p>

<button
  class="btn btn-primary disabled placeholder col-4"
  aria-hidden="true"
></button>
```

#### Popover (Requires Popper.js)

```html
<button
  type="button"
  class="btn btn-lg btn-danger"
  data-bs-toggle="popover"
  title="Popover title"
  data-bs-content="And here's some amazing content."
>
  Click to toggle popover
</button>

<button
  type="button"
  class="btn btn-secondary"
  data-bs-container="body"
  data-bs-toggle="popover"
  data-bs-placement="top"
  data-bs-content="Top popover"
>
  Popover on top
</button>
```

#### Progress

```html
<div
  class="progress"
  role="progressbar"
  aria-label="Basic example"
  aria-valuenow="0"
  aria-valuemin="0"
  aria-valuemax="100"
>
  <div class="progress-bar" style="width: 0%"></div>
</div>

<div class="progress">
  <div
    class="progress-bar w-75"
    role="progressbar"
    aria-valuenow="75"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    75%
  </div>
</div>

<div class="progress">
  <div class="progress-bar bg-success" style="width: 25%">Success</div>
</div>

<div class="progress">
  <div class="progress-bar progress-bar-striped" style="width: 10%">
    Striped
  </div>
</div>

<div class="progress">
  <div
    class="progress-bar progress-bar-striped progress-bar-animated"
    style="width: 75%"
  >
    Animated
  </div>
</div>

<div class="progress-stacked">
  <div class="progress" style="width: 30%">...</div>
  <div class="progress" style="width: 20%">...</div>
</div>
```

#### Scrollspy

```html
<nav id="navbar-example2" class="navbar bg-body-tertiary px-3 mb-3">
  <a class="navbar-brand" href="#">Navbar</a>
  <ul class="nav nav-pills">
    <li class="nav-item">
      <a class="nav-link" href="#scrollspyHeading1">First</a>
    </li>
    <li class="nav-item">
      <a class="nav-link" href="#scrollspyHeading2">Second</a>
    </li>
  </ul>
</nav>
<div
  data-bs-spy="scroll"
  data-bs-target="#navbar-example2"
  data-bs-root-margin="0px 0px -40%"
  data-bs-threshold="0.1"
  tabindex="0"
>
  <h4 id="scrollspyHeading1">First heading</h4>
  <p>Content...</p>
  <h4 id="scrollspyHeading2">Second heading</h4>
  <p>Content...</p>
</div>
```

#### Spinners

```html
<div class="spinner-border text-primary" role="status">
  <span class="visually-hidden">Loading...</span>
</div>
<div class="spinner-border text-secondary" role="status"></div>
<div class="spinner-border text-success" role="status"></div>

<div class="spinner-grow text-primary" role="status">
  <span class="visually-hidden">Loading...</span>
</div>

<div class="spinner-border spinner-border-sm" role="status"></div>
<div class="spinner-grow spinner-grow-sm" role="status"></div>

<button class="btn btn-primary" type="button" disabled>
  <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
  <span class="visually-hidden" role="status">Loading...</span>
  Loading...
</button>
```

#### Toasts

```html
<div class="toast" role="alert" aria-live="assertive" aria-atomic="true">
  <div class="toast-header">
    <img src="..." class="rounded me-2" alt="..." />
    <strong class="me-auto">Bootstrap</strong>
    <small>11 mins ago</small>
    <button
      type="button"
      class="btn-close"
      data-bs-dismiss="toast"
      aria-label="Close"
    ></button>
  </div>
  <div class="toast-body">Hello, world!</div>
</div>

<div class="toast align-items-center text-bg-primary border-0" role="alert">
  Color variant
</div>

<div class="toast-container position-fixed top-0 end-0 p-3">
  Positioned container
</div>
```

#### Tooltip (Requires Popper.js)

```html
<button
  type="button"
  class="btn btn-secondary"
  data-bs-toggle="tooltip"
  data-bs-placement="top"
  title="Tooltip on top"
>
  Tooltip on top
</button>
<button
  type="button"
  class="btn btn-secondary"
  data-bs-toggle="tooltip"
  data-bs-placement="right"
  title="Tooltip on right"
>
  Tooltip on right
</button>
<button
  type="button"
  class="btn btn-secondary"
  data-bs-toggle="tooltip"
  data-bs-placement="bottom"
  title="Tooltip on bottom"
>
  Tooltip on bottom
</button>
<button
  type="button"
  class="btn btn-secondary"
  data-bs-toggle="tooltip"
  data-bs-placement="left"
  title="Tooltip on left"
>
  Tooltip on left
</button>

<button
  type="button"
  class="btn btn-secondary"
  data-bs-toggle="tooltip"
  data-bs-html="true"
  title="<em>Tooltip</em> <u>with</u> <b>HTML</b>"
>
  Tooltip with HTML
</button>
```

## JavaScript Initialization

Most components auto-initialize via data attributes. For manual control:

```js
const tooltipTriggerList = document.querySelectorAll(
  '[data-bs-toggle="tooltip"]',
);
const tooltipList = [...tooltipTriggerList].map(
  (tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl),
);

const popoverTriggerList = document.querySelectorAll(
  '[data-bs-toggle="popover"]',
);
const popoverList = [...popoverTriggerList].map(
  (popoverTriggerEl) => new bootstrap.Popover(popoverTriggerEl),
);

const myModal = new bootstrap.Modal(
  document.getElementById("myModal"),
  options,
);
const myDropdown = new bootstrap.Dropdown(
  document.getElementById("myDropdown"),
  options,
);
const myCollapse = new bootstrap.Collapse(
  document.getElementById("myCollapse"),
  options,
);
const myOffcanvas = new bootstrap.Offcanvas(
  document.getElementById("myOffcanvas"),
  options,
);
const myToast = new bootstrap.Toast(
  document.getElementById("myToast"),
  options,
);
const myTab = new bootstrap.Tab(document.getElementById("myTab"), options);
const myAlert = new bootstrap.Alert(document.getElementById("myAlert"));
const myButton = new bootstrap.Button(document.getElementById("myButton"));
```
