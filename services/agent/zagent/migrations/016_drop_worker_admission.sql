DROP FUNCTION IF EXISTS public.register_worker_pod(text, uuid, text);
DROP TABLE IF EXISTS privacy.worker_pods;
DO $$ BEGIN
    DROP ROLE IF EXISTS zagent_worker;
EXCEPTION WHEN dependent_objects_still_exist THEN
    -- Another database on this server has not applied this migration yet.
    NULL;
END $$;
