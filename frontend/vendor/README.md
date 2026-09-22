# Shared UI build

`terry-react-ui-library-0.2.1-shotmill.11.tgz` is a locally built release of
Terry React UI Library, based on commit
`ba1474ac56ad9b15a2f09d51a1c910b811b83ec9`. It is not a parallel widget implementation.

The adjacent source patch adds a public `--tc-button-radius` token, `size="icon"`,
native button accessibility attributes, and a shared `RangeSlider` with Showcase
examples. The release also adds public `Modal` / `useModalPortalTarget`, adopts
native dialog modality in shared `Dialog`, and gives `Select` keyboard navigation,
Escape dismissal, and trigger focus restoration. Existing defaults remain compatible. ShotMill opts into capsule buttons
through the public token.

RangeSlider uses one coordinate system for both handles and the selected interval.
Pointer capture retains dragging outside the control; local draft updates keep the
handles and labels responsive while parent notifications are limited to 48 ms.
Pointer release/cancel flushes the last value immediately. Keyboard arrows, Page
Up/Down, Home/End, disabled state, fractional values and overlapping hit areas are
covered by browser acceptance. Showcase checks include light/dark at 200% zoom.
Task-specific duration defaults stay in ShotMill; track geometry, focus and pointer
behavior belong to the shared library.

RangeSlider also offers `variant="timeline"`: a time ruler and a movable clip.
Dragging its body translates both endpoints and preserves duration; dragging edges
trims the interval. Pointer capture continues outside the track, bounds clamp the
whole clip, and keyboard arrows / Home / End move the selected clip. The ordinary
slider variant remains available. Both are mounted in the real Showcase.

Filled action buttons now derive a darker fill from Accent so white text remains
readable in both modes and on hover. Selected segments derive a light/dark text
tone from Accent, while unselected light controls use semantic text colors instead
of a pale mix of Base. Geometry and the five public theme channels are unchanged.
Actual React Button and SegmentedControl examples in Showcase are measured in both
modes at both viewport sizes; the product has a separate contrast regression.

The actual React Showcase mounts a nested modal and searchable Select example.
Browser acceptance covers initial focus, Tab containment, background isolation,
nested Escape order, and focus restoration in both themes at 1366 × 768 and
960 × 540 CSS pixels (the layout viewport of a 1920 × 1080 screen at 200%).
Reduced motion is checked separately. This is not a screen-reader or complete
contrast audit.

Rebuild: check out the base commit in the upstream repository, apply
`terry-ui-capsule.patch`, install its dependencies, run `build:lib` and pack it.
The tarball is checked in so installation does not rely on the temporary source
checkout or mutate `node_modules`. No upstream commit has been pushed.

This is a versioned dependency snapshot, not a temporary runtime patch. Keep the
source patch with the archive until the shared library publishes these changes;
then replace both with a pinned upstream release. Local reconstruction checkouts
can be removed without affecting installation.

Archive SHA256:
`861b8bb464446be3e930feb559fb9a0f56c5f8802ae83ae5349075522041c601`

Select now portals into the current Modal layer (or body), preserves theme variables, measures the viewport, and wraps long menu labels. Trigger and Slider wrappers shrink within their owning layout. Slider exposes ariaLabel. Real Showcase includes a clipped narrow Select/Slider row, search and disabled states. Evidence: .artifacts/experience-layout/.

The Checkbox media variant provides a 24px translucent rounded-square selection control, with checked and disabled examples in the base showcase. Task cards use this variant; list checkboxes retain their default style.
