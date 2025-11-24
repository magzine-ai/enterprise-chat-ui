/**
 * Typed Redux Hooks
 * 
 * Provides typed versions of Redux hooks for better TypeScript support.
 * 
 * Hooks:
 * - useAppDispatch: Typed dispatch function
 * - useAppSelector: Typed selector hook with RootState
 * 
 * Usage:
 * ```typescript
 * const dispatch = useAppDispatch();
 * const messages = useAppSelector(state => state.messages.messagesByConversation[1]);
 * ```
 */
import { useDispatch, useSelector } from 'react-redux';
import type { RootState, AppDispatch } from './index';

export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector = <T>(selector: (state: RootState) => T) => useSelector(selector);

