-- Keep cloud and legacy local databases aligned with the lowercase API values.
DO $$
BEGIN
    IF to_regtype('tree_status_enum') IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'HEALTHY')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'healthy') THEN
            ALTER TYPE tree_status_enum RENAME VALUE 'HEALTHY' TO 'healthy';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'INFECTED')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'infected') THEN
            ALTER TYPE tree_status_enum RENAME VALUE 'INFECTED' TO 'infected';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'BAGGED')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'bagged') THEN
            ALTER TYPE tree_status_enum RENAME VALUE 'BAGGED' TO 'bagged';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'DEAD')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_status_enum'::regtype AND enumlabel = 'dead') THEN
            ALTER TYPE tree_status_enum RENAME VALUE 'DEAD' TO 'dead';
        END IF;
    END IF;

    IF to_regtype('tree_stage_enum') IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'DORMANT')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'dormant') THEN
            ALTER TYPE tree_stage_enum RENAME VALUE 'DORMANT' TO 'dormant';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'FLOWERING')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'flowering') THEN
            ALTER TYPE tree_stage_enum RENAME VALUE 'FLOWERING' TO 'flowering';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'FRUITLET')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'fruitlet') THEN
            ALTER TYPE tree_stage_enum RENAME VALUE 'FRUITLET' TO 'fruitlet';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'MATURE')
           AND NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'tree_stage_enum'::regtype AND enumlabel = 'mature') THEN
            ALTER TYPE tree_stage_enum RENAME VALUE 'MATURE' TO 'mature';
        END IF;
    END IF;
END $$;

ALTER TABLE IF EXISTS tree ALTER COLUMN status SET DEFAULT 'healthy';
ALTER TABLE IF EXISTS tree ALTER COLUMN current_stage SET DEFAULT 'dormant';
