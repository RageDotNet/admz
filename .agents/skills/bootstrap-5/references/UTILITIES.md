# Bootstrap 5 Utilities Reference

## Complete Utility Classes Quick Reference

### Background

```css
.bg-primary, .bg-secondary, .bg-success, .bg-danger, .bg-warning, .bg-info, .bg-light, .bg-dark, .bg-body, .bg-white, .bg-transparent, .bg-black
.bg-body-secondary, .bg-body-tertiary
.bg-primary-subtle, .bg-secondary-subtle, .bg-success-subtle, .bg-danger-subtle, .bg-warning-subtle, .bg-info-subtle, .bg-light-subtle, .bg-dark-subtle
.bg-gradient
.bg-opacity-10, .bg-opacity-25, .bg-opacity-50, .bg-opacity-75, .bg-opacity-100
```

### Borders

```css
.border, .border-top, .border-end, .border-bottom, .border-start
.border-0, .border-top-0, .border-end-0, .border-bottom-0, .border-start-0
.border-primary, .border-secondary, .border-success, .border-danger, .border-warning, .border-info, .border-light, .border-dark, .border-white, .border-black
.border-opacity-10, .border-opacity-25, .border-opacity-50, .border-opacity-75, .border-opacity-100
.rounded, .rounded-top, .rounded-end, .rounded-bottom, .rounded-start, .rounded-circle, .rounded-pill
.rounded-0, .rounded-1, .rounded-2, .rounded-3, .rounded-4, .rounded-5
```

### Colors (Text)

```css
.text-primary, .text-secondary, .text-success, .text-danger, .text-warning, .text-info, .text-light, .text-dark
.text-body, .text-body-secondary, .text-body-tertiary
.text-primary-emphasis, .text-secondary-emphasis, .text-success-emphasis, .text-danger-emphasis, .text-warning-emphasis, .text-info-emphasis, .text-light-emphasis, .text-dark-emphasis
.text-black, .text-white, .text-black-50, .text-white-50
.text-muted (deprecated in 5.3)
.text-opacity-25, .text-opacity-50, .text-opacity-75, .text-opacity-100
```

### Display

```css
.d-none, .d-inline, .d-inline-block, .d-block, .d-grid, .d-table, .d-table-cell, .d-table-row, .d-flex, .d-inline-flex
.d-{breakpoint}-none, .d-{breakpoint}-inline, .d-{breakpoint}-inline-block, .d-{breakpoint}-block, .d-{breakpoint}-grid, .d-{breakpoint}-table, .d-{breakpoint}-table-cell, .d-{breakpoint}-table-row, .d-{breakpoint}-flex, .d-{breakpoint}-inline-flex
```

### Flexbox

```css
/* Direction */
.flex-row, .flex-column, .flex-row-reverse, .flex-column-reverse
.flex-{breakpoint}-row, .flex-{breakpoint}-column, .flex-{breakpoint}-row-reverse, .flex-{breakpoint}-column-reverse

/* Justify Content */
.justify-content-start, .justify-content-end, .justify-content-center, .justify-content-between, .justify-content-around, .justify-content-evenly
.justify-content-{breakpoint}-start, .justify-content-{breakpoint}-end, .justify-content-{breakpoint}-center, .justify-content-{breakpoint}-between, .justify-content-{breakpoint}-around, .justify-content-{breakpoint}-evenly

/* Align Items */
.align-items-start, .align-items-end, .align-items-center, .align-items-baseline, .align-items-stretch
.align-items-{breakpoint}-start, .align-items-{breakpoint}-end, .align-items-{breakpoint}-center, .align-items-{breakpoint}-baseline, .align-items-{breakpoint}-stretch

/* Align Self */
.align-self-start, .align-self-end, .align-self-center, .align-self-baseline, .align-self-stretch

/* Fill */
.flex-fill, .flex-{breakpoint}-fill

/* Grow/Shrink */
.flex-grow-0, .flex-grow-1, .flex-shrink-0, .flex-shrink-1

/* Wrap */
.flex-wrap, .flex-nowrap, .flex-wrap-reverse

/* Order */
.order-first, .order-0, .order-1, .order-2, .order-3, .order-4, .order-5, .order-last

/* Align Content */
.align-content-start, .align-content-end, .align-content-center, .align-content-between, .align-content-around, .align-content-stretch
```

### Float

```css
.float-start, .float-end, .float-none
.float-{breakpoint}-start, .float-{breakpoint}-end, .float-{breakpoint}-none
```

### Interactions

```css
.user-select-all, .user-select-auto, .user-select-none
.pointer-event, .pointer-events-none
```

### Link

```css
.link-primary, .link-secondary, .link-success, .link-danger, .link-warning, .link-info, .link-light, .link-dark
.link-body-emphasis, .link-underline, .link-underline-opacity-0, .link-underline-opacity-10, .link-underline-opacity-25, .link-underline-opacity-50, .link-underline-opacity-75, .link-underline-opacity-100
.link-offset-1, .link-offset-2, .link-offset-3
```

### Object Fit

```css
.object-fit-contain, .object-fit-cover, .object-fit-fill, .object-fit-scale, .object-fit-none
.object-fit-{breakpoint}-contain, .object-fit-{breakpoint}-cover, .object-fit-{breakpoint}-fill, .object-fit-{breakpoint}-scale, .object-fit-{breakpoint}-none
```

### Opacity

```css
.opacity-0, .opacity-25, .opacity-50, .opacity-75, .opacity-100
```

### Overflow

```css
.overflow-auto, .overflow-hidden, .overflow-visible, .overflow-scroll
.overflow-x-auto, .overflow-x-hidden, .overflow-x-visible, .overflow-x-scroll
.overflow-y-auto, .overflow-y-hidden, .overflow-y-visible, .overflow-y-scroll
```

### Position

```css
.position-static, .position-relative, .position-absolute, .position-fixed, .position-sticky
.fixed-top, .fixed-bottom
.sticky-top, .sticky-bottom
.top-0, .top-50, .top-100
.bottom-0, .bottom-50, .bottom-100
.start-0, .start-50, .start-100
.end-0, .end-50, .end-100
.translate-middle, .translate-middle-x, .translate-middle-y
```

### Shadows

```css
.shadow-none, .shadow-sm, .shadow, .shadow-lg
```

### Sizing

```css
/* Width */
.w-25, .w-50, .w-75, .w-100, .w-auto
.mw-100, .mw-auto
.vw-25, .vw-50, .vw-75, .vw-100
.min-vw-100

/* Height */
.h-25, .h-50, .h-75, .h-100, .h-auto
.mh-100, .mh-auto
.vh-25, .vh-50, .vh-75, .vh-100
.min-vh-25, .min-vh-50, .min-vh-75, .min-vh-100
```

### Spacing

```css
/* Format: {property}{sides}-{size} or {property}{sides}-{breakpoint}-{size} */
/* Property: m (margin), p (padding) */
/* Sides: t, b, s (start), e (end), x, y, (blank) */
/* Size: 0, 1, 2, 3, 4, 5, auto */

.m-0, .m-1, .m-2, .m-3, .m-4, .m-5, .m-auto
.mt-0, .mt-1, .mt-2, .mt-3, .mt-4, .mt-5, .mt-auto
.mb-0, .mb-1, .mb-2, .mb-3, .mb-4, .mb-5, .mb-auto
.ms-0, .ms-1, .ms-2, .ms-3, .ms-4, .ms-5, .ms-auto
.me-0, .me-1, .me-2, .me-3, .me-4, .me-5, .me-auto
.mx-0, .mx-1, .mx-2, .mx-3, .mx-4, .mx-5, .mx-auto
.my-0, .my-1, .my-2, .my-3, .my-4, .my-5, .my-auto

.p-0, .p-1, .p-2, .p-3, .p-4, .p-5
.pt-0, .pt-1, .pt-2, .pt-3, .pt-4, .pt-5
.pb-0, .pb-1, .pb-2, .pb-3, .pb-4, .pb-5
.ps-0, .ps-1, .ps-2, .ps-3, .ps-4, .ps-5
.pe-0, .pe-1, .pe-2, .pe-3, .pe-4, .pe-5
.px-0, .px-1, .px-2, .px-3, .px-4, .px-5
.py-0, .py-1, .py-2, .py-3, .py-4, .py-5

/* Gap (for flex/grid) */
.gap-0, .gap-1, .gap-2, .gap-3, .gap-4, .gap-5
.gx-0, .gx-1, .gx-2, .gx-3, .gx-4, .gx-5
.gy-0, .gy-1, .gy-2, .gy-3, .gy-4, .gy-5
```

### Text

```css
/* Alignment */
.text-start, .text-center, .text-end
.text-{breakpoint}-start, .text-{breakpoint}-center, .text-{breakpoint}-end

/* Wrap */
.text-wrap, .text-nowrap

/* Break */
.text-break

/* Transform */
.text-lowercase, .text-uppercase, .text-capitalize

/* Weight/Italics */
.fw-lighter, .fw-light, .fw-normal, .fw-medium, .fw-semibold, .fw-bold, .fw-bolder
.fst-normal, .fst-italic

/* Line Height */
.lh-1, .lh-sm, .lh-base, .lh-lg

/* Monospace */
.font-monospace

/* Reset */
.text-reset

/* Decoration */
.text-decoration-none, .text-decoration-underline, .text-decoration-line-through

/* Size */
.fs-1, .fs-2, .fs-3, .fs-4, .fs-5, .fs-6

/* Truncate */
.text-truncate
```

### Vertical Align

```css
.align-baseline, .align-top, .align-middle, .align-bottom, .align-text-top, .align-text-bottom
```

### Visibility

```css
.visible, .invisible
```

### Z-index

```css
.z-n1, .z-0, .z-1, .z-2, .z-3
.z-sm-0, .z-md-0, .z-lg-0, .z-xl-0, .z-xxl-0
```

## Spacing Scale

| Class  | Size                           |
| ------ | ------------------------------ |
| `0`    | 0                              |
| `1`    | $spacer \* .25 (0.25rem = 4px) |
| `2`    | $spacer \* .5 (0.5rem = 8px)   |
| `3`    | $spacer (1rem = 16px)          |
| `4`    | $spacer \* 1.5 (1.5rem = 24px) |
| `5`    | $spacer \* 3 (3rem = 48px)     |
| `auto` | auto                           |

## Z-index Scale

| Component          | Z-index |
| ------------------ | ------- |
| Dropdown           | 1000    |
| Sticky             | 1020    |
| Fixed              | 1030    |
| Offcanvas backdrop | 1040    |
| Offcanvas          | 1045    |
| Modal backdrop     | 1050    |
| Modal              | 1055    |
| Popover            | 1070    |
| Tooltip            | 1080    |
| Toast              | 1090    |

## Print Utilities

```css
.d-print-none, .d-print-inline, .d-print-inline-block, .d-print-block, .d-print-grid, .d-print-table, .d-print-table-cell, .d-print-table-row, .d-print-flex, .d-print-inline-flex
```
