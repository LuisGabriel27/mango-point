export function runWhenMapReady(map, hasLoaded, update) {
  // loaded() becomes false again while sources or tiles are rendering, but
  // the load event only fires once. After initial load, always apply updates.
  if (hasLoaded) update()
  else map.once('load', update)

  return () => map.off('load', update)
}
