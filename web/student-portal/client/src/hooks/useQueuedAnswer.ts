import { useEffect } from 'react';
import { useAppDispatch } from '../store';
import { useQueuedQuery } from '../store/api';
import { queueUpdated } from '../store/chatSlice';

const POLL_MS = 3000;

export function useQueuedAnswer(queueId: string | undefined) {
  const dispatch = useAppDispatch();
  const { data } = useQueuedQuery(queueId ?? '', { skip: !queueId, pollingInterval: POLL_MS });

  useEffect(() => {
    if (queueId && data) dispatch(queueUpdated({ queueId, ...data }));
  }, [dispatch, queueId, data]);
}
