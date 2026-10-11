import { createContext, useContext } from 'react'

// Presentation overrides never replace the user's underlying form or panel state.
export const TourPresentationContext = createContext(null)
export const useTourPresentation = () => useContext(TourPresentationContext)
