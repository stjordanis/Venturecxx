{-# LANGUAGE FlexibleContexts, TemplateHaskell, TypeSynonymInstances, FlexibleInstances, ExistentialQuantification, RecordWildCards, TupleSections #-}

module Trace where

import Debug.Trace
import Data.Maybe hiding (fromJust)
import qualified Data.Map as M
import qualified Data.Set as S
import Control.Lens hiding (children)  -- from cabal install lens
import Control.Monad.State hiding (state) -- :set -hide-package monads-tf-0.1.0.1
import Control.Monad.Writer.Class
import Control.Monad.Reader
import Control.Monad.State.Class
import Control.Monad.Morph
import Text.PrettyPrint -- presumably from cabal install pretty

import Utils
import Language hiding (Value, Exp, Env)
import qualified Language as L

----------------------------------------------------------------------
-- Small objects                                                    --
----------------------------------------------------------------------

type Value = L.Value SPAddress
type Exp = L.Exp Value
type Env = L.Env String Address

class Valuable b where
    fromValue :: Value -> Maybe b

instance Valuable Double where
    fromValue (Number d) = Just d
    fromValue _ = Nothing

instance Valuable Bool where
    fromValue (Boolean b) = Just b
    fromValue _ = Nothing

instance Valuable SPAddress where
    fromValue (Procedure a) = Just a
    fromValue _ = Nothing

instance Valuable Value where
    fromValue = Just

newtype Address = Address Unique
    deriving (Eq, Ord, Show)

newtype SPAddress = SPAddress Unique
    deriving (Eq, Ord, Show)

newtype SRId = SRId Unique
    deriving (Eq, Ord, Show)

data SimulationRequest = SimulationRequest SRId Exp Env
    deriving Show

srid :: SimulationRequest -> SRId
srid (SimulationRequest id _ _) = id

----------------------------------------------------------------------
-- Stochastic Procedure Interface                                   --
----------------------------------------------------------------------

-- m is the type of randomness source that this SP uses, presumably an
-- instance of MonadRandom.
-- a is the type of the state that mediates any exchangeable coupling
-- between this SP's outputs.  For most SPs, a = ().  a is existential, per
-- http://www.haskell.org/haskellwiki/Heterogenous_collections#Existential_types
-- because I wish to be able to store SPs in homogeneous data structures.

-- The collection of objects (incorporate v) U (unincorporate v) is
-- expected to form an _Abelian_ group acting on a (except for v on
-- which they error out).  Further, for any given v, (unincorporate v)
-- and (incorporate v) are expected to be inverses.
data SP m = forall a. (Show a) => SP
    { requester :: SPRequester m a
    , log_d_req :: Maybe (a -> [Address] -> [SimulationRequest] -> Double)
    , outputter :: SPOutputter m a
    , log_d_out :: Maybe (a -> [Node] -> [Node] -> Value -> Double)
    , current :: a
    -- These guys may need to accept the argument lists, but I have
    -- not yet seen an example that forces this.
    , incorporate :: Value -> a -> a
    , unincorporate :: Value -> a -> a
    , incorporateR :: [Value] -> [SimulationRequest] -> a -> a
    , unincorporateR :: [Value] -> [SimulationRequest] -> a -> a
    }
-- TODO Can I refactor this data type to capture the fact that
-- deterministic requesters and outputters never have meaningful log_d
-- components, whereas stochastic ones may or may not?

-- These functions appear to be necessary to avoid a bizarre compile
-- error in GHC, per
-- http://breaks.for.alienz.org/blog/2011/10/21/record-update-for-insufficiently-polymorphic-field/
do_inc :: Value -> SP m -> SP m
do_inc v SP{..} = SP{ current = incorporate v current, ..}

do_uninc :: Value -> SP m -> SP m
do_uninc v SP{..} = SP{ current = unincorporate v current, ..}

do_incR :: [Value] -> [SimulationRequest] -> SP m -> SP m
do_incR vs rs SP{..} = SP{ current = incorporateR vs rs current, ..}

do_unincR :: [Value] -> [SimulationRequest] -> SP m -> SP m
do_unincR vs rs SP{..} = SP{ current = unincorporateR vs rs current, ..}

instance Show (SP m) where
    show SP{current = s} = "A stochastic procedure with state " ++ show s

data SPRequester m a = DeterministicR (a -> [Address] -> UniqueSource [SimulationRequest])
                     | RandomR (a -> [Address] -> UniqueSourceT m [SimulationRequest])
                     | ReaderR (a -> [Address] -> ReaderT (Trace m) UniqueSource [SimulationRequest])

data SPOutputter m a = Trivial
                     | DeterministicO (a -> [Node] -> [Node] -> Value)
                     | RandomO (a -> [Node] -> [Node] -> m Value)
                     | SPMaker (a -> [Node] -> [Node] -> SP m) -- Are these ever random?
                     | ReferringSPMaker (a -> [Address] -> [Address] -> SP m)

asRandomR :: (Monad m) => SPRequester m a -> a -> [Address] -> ReaderT (Trace m) (UniqueSourceT m) [SimulationRequest]
asRandomR (RandomR f) st as = lift $ f st as
asRandomR (DeterministicR f) st as = lift $ returnT $ f st as
asRandomR (ReaderR f) st as = hoist returnT $ f st as

isRandomR :: SPRequester m a -> Bool
isRandomR (RandomR _) = True
isRandomR (DeterministicR _) = False
isRandomR (ReaderR _) = False

asRandomO :: (Monad m) => SPOutputter m a -> a -> [Node] -> [Node] -> Either (m Value) (SP m)
asRandomO Trivial _ _ (r0:_) = Left $ return $ fromJust "Trivial outputter node had no value" $ valueOf r0
asRandomO Trivial _ _ _ = error "Trivial outputter requires one response"
asRandomO (RandomO f) st args reqs = Left $ f st args reqs
asRandomO (DeterministicO f) st args reqs = Left $ return $ f st args reqs
asRandomO (SPMaker f) st args reqs = Right $ f st args reqs
asRandomO _ _ _ _ = error "Should never pass ReferringSPMaker to asRandomO"

asRandomO' :: (Monad m) => SPOutputter m a -> a -> [Address] -> [Address] -> Trace m -> Either (m Value) (SP m)
asRandomO' (ReferringSPMaker f) a argAs resultAs _ = Right $ f a argAs resultAs
asRandomO' out a argAs resultAs Trace{ _nodes = ns} = asRandomO out a args results where
  args = map (fromJust "Running outputter for an output with a missing parent" . flip M.lookup ns) argAs
  results = map (fromJust "Running outputter for an output with a missing request result" . flip M.lookup ns) resultAs

isRandomO :: SPOutputter m a -> Bool
isRandomO Trivial = False
isRandomO (RandomO _) = True
isRandomO (DeterministicO _) = False
isRandomO (SPMaker _) = False
isRandomO (ReferringSPMaker _) = False

----------------------------------------------------------------------
-- Nodes                                                            --
----------------------------------------------------------------------

data Node = Constant Value
          | Reference (Maybe Value) Address
          | Request (Maybe [SimulationRequest]) (Maybe Address) Address [Address]
          | Output (Maybe Value) Address Address [Address] [Address]
    deriving Show

valueOf :: Node -> Maybe Value
valueOf (Constant v) = Just v
valueOf (Reference v _) = v
valueOf (Output v _ _ _ _) = v
valueOf _ = Nothing

revalue :: Node -> Maybe Value -> Node
revalue (Constant _) _ = error "Cannot revalue a constant"
revalue (Reference _ a) v = Reference v a
-- This is a slight violation of the lens laws
revalue (Request _ outA a as) Nothing = Request Nothing outA a as
revalue r@(Request _ _ _ _) _ = r
revalue (Output _ reqA opa args reqs) v = Output v reqA opa args reqs

value :: Simple Lens Node (Maybe Value)
value = lens valueOf revalue

isRegenerated :: Node -> Bool
isRegenerated (Constant _) = True
isRegenerated (Reference Nothing _) = False
isRegenerated (Reference (Just _) _) = True
isRegenerated (Request Nothing _ _ _) = False
isRegenerated (Request (Just _) _ _ _) = True
isRegenerated (Output Nothing _ _ _ _) = False
isRegenerated (Output (Just _) _ _ _ _) = True

sim_reqs :: Simple Lens Node (Maybe [SimulationRequest])
sim_reqs = lens _requests re_requests where
    _requests (Request r _ _ _) = r
    _requests _ = Nothing
    re_requests (Request _ outA a args) r = (Request r outA a args)
    re_requests n Nothing = n
    re_requests _ _ = error "Trying to set requests for a non-request node."

parentAddrs :: Node -> [Address]
parentAddrs (Constant _) = []
parentAddrs (Reference _ addr) = [addr]
parentAddrs (Request _ _ a as) = a:as
parentAddrs (Output _ reqA a as as') = reqA:a:(as ++ as')

opAddr :: Node -> Maybe Address
opAddr (Request _ _ a _) = Just a
opAddr (Output _ _ a _ _) = Just a
opAddr _ = Nothing

requestIds :: Node -> [SRId]
requestIds (Request (Just srs) _ _ _) = map srid srs
requestIds _ = error "Asking for request IDs of a non-request node"

addOutput :: Address -> Node -> Node
addOutput outA (Request v _ a as) = Request v (Just outA) a as
addOutput _ n = n

out_node :: Simple Setter Node (Maybe Address)
out_node = sets _out_node where
    _out_node f (Request v outA a as) = Request v (f outA) a as
    _out_node _ _ = error "Non-Request nodes do not have corresponding output nodes"

responses :: Simple Lens Node [Address]
responses = lens _responses addResponses where
    _responses (Output _ _ _ _ rs) = rs
    _responses _ = []
    addResponses (Output v reqA a as _) resps = Output v reqA a as resps
    addResponses n _ = n

-- Can the given node, which is an application of the given SP, absorb
-- a change to the given address (which is expected to be one of its
-- parents).
canAbsorb :: Node -> Address -> SP m -> Bool
canAbsorb (Request _ _ opA _)      a _                        | opA  == a = False
canAbsorb (Request _ _ _ _)        _ SP{log_d_req = (Just _)}             = True
canAbsorb (Output _ reqA _ _ _)    a _                        | reqA == a = False
canAbsorb (Output _ _ opA _ _)     a _                        | opA  == a = False
canAbsorb (Output _ _ _ _ (fst:_)) a SP{outputter = Trivial}  | fst  == a = False
canAbsorb (Output _ _ _ _ _)       _ SP{outputter = Trivial}              = True
canAbsorb (Output _ _ _ _ _)       _ SP{log_d_out = (Just _)}             = True
canAbsorb _ _ _ = False

----------------------------------------------------------------------
-- Traces                                                           --
----------------------------------------------------------------------

-- A "torus" is a trace some of whose nodes have Nothing values, and
-- some of whose Request nodes may have outstanding SimulationRequests
-- that have not yet been met.
data Trace rand =
    Trace { _nodes :: (M.Map Address Node)
          , _randoms :: S.Set Address
          , _node_children :: M.Map Address (S.Set Address)
          , _sprs :: (M.Map SPAddress (SPRecord rand))
          , _addr_seed :: UniqueSeed
          , _spaddr_seed :: UniqueSeed
          }
    deriving Show

data SPRecord m = SPRecord { sp :: (SP m)
                           , srid_seed :: UniqueSeed
                           , requests :: M.Map SRId Address
                           }
    deriving Show

spRecord :: SP m -> SPRecord m
spRecord sp = SPRecord sp uniqueSeed M.empty

----------------------------------------------------------------------
-- Basic Trace Manipulations                                        --
----------------------------------------------------------------------

-- The operations in this group neither expect nor conserve any
-- invariants not enforced by the type system.

makeLenses ''Trace

empty :: Trace m
empty = Trace M.empty S.empty M.empty M.empty uniqueSeed uniqueSeed

fromValueAt :: Valuable b => Address -> Trace m -> Maybe b
fromValueAt a t = (t^. nodes . at a) >>= valueOf >>= fromValue

operatorRecord :: Node -> Trace m -> Maybe (SPRecord m)
operatorRecord n t = opAddr n >>= (flip fromValueAt t) >>= (\addr -> t ^. sprs . at addr)

operator :: Node -> Trace m -> Maybe (SP m)
operator n = liftM sp . operatorRecord n

isRandomNode :: Node -> Trace m -> Bool
isRandomNode n@(Request _ _ _ _) t = case operator n t of
                                       Nothing -> False
                                       (Just SP{requester = req}) -> isRandomR req
isRandomNode n@(Output _ _ _ _ _) t = case operator n t of
                                        Nothing -> False
                                        (Just SP{outputter = out}) -> isRandomO out
isRandomNode _ _ = False

----------------------------------------------------------------------
-- Structural Trace Manipulations                                   --
----------------------------------------------------------------------

-- These operations demand and preserve structural validity of the
-- trace.  Structural validity is about the interlinks between nodes
-- and has no dependence on any values they may or may not contain.

-- More precisely, a trace is "valid" if
-- 1. Every Address held by the trace points to a Node in the trace
--    (i.e. occurs as a key in the _nodes map)
-- 2. Every SPAddress held by the trace points to an SPRecord in the
--    trace (i.e. occurs as a key in the _sprs map)
-- 3. The node children maps are be right, to wit A is recorded as a
--    child of B iff A is in the trace and the address of B appears in
--    the list of parentAddrs of A.
-- 4. The seeds are right, to wit
--    a. The _addr_seed exceeds every Address that appears in the
--       trace;
--    b. The _spaddr_seed exceeds every SPAddress that appears in the
--       trace; and
--    c. For each SPRecord r in the trace, the _srid_seed of r exceeds
--       every SRId that appears in r's requests map, as well as every
--       SRId that appears in any SimulationRequest of any Request
--       node whose operatorRecord is Just r.

-- 5. Request and Output nodes come in pairs, determined by the reqA
--    address of the Output node:
--    a. The reqA address of every Output node points to a Request node
--    b. Every Request node is thus pointed to at most once
--    c. The operator and argument lists of every such pair are equal
--    d. If it is not Nothing, the outA address of a Request node
--       points to the Output node that points to it.
-- 6. Distinct (SPAddress,SRId) pairs map to distinct Addresses
--    through the SPRecords.

-- An Address is "referenced by" a valid trace iff it occurs in any of
-- its Nodes or SPRecords (but the node_children map doesn't count).

-- I should be able to construct a valid trace from a valid pair of
-- nodes and sprs maps.

-- The "randoms" field can really only be defined in the presence of
-- stricter conditions, such as well-typedness (e.g., nodes that occur
-- in operator position contain values that are procedures)
-- - given a suitable notion of well-typedness (and presence of
--   values), 1 and 2 together imply that the operatorRecord of any
--   Request or Output Node in the trace is not Nothing.

lookupNode :: Address -> Trace m -> Maybe Node
lookupNode a t = t ^. nodes . at a

-- If the given Trace is valid and the given Address is not referenced
-- in it, returns a valid Trace with that node deleted.
deleteNode :: Address -> Trace m -> Trace m
deleteNode a t@Trace{_nodes = ns, _randoms = rs, _node_children = cs} =
    t{ _nodes = ns', _randoms = rs', _node_children = cs'' } where
        node = fromJust "Deleting a non-existent node" $ M.lookup a ns
        ns' = M.delete a ns
        rs' = S.delete a rs -- OK even if it wasn't random
        cs' = dropChildOf a (parentAddrs node) cs
        cs'' = M.delete a cs'

dropChildOf :: (Ord c, Ord p) => c -> [p] -> M.Map p (S.Set c) -> M.Map p (S.Set c)
dropChildOf c ps m = foldl dropChild m ps
    where dropChild m p = M.adjust (S.delete c) p m

-- If the given Trace is valid and every Address in the given Node
-- points to a Node in the given Trace, returns a unique Address
-- (distinct from every other Address in the trace) and a valid Trace
-- with that Node added at that Address.
-- N.B. addFreshNode cannot be a Setter because it is not idempotent
addFreshNode :: Node -> Trace m -> (Address, Trace m)
addFreshNode node t@Trace{ _nodes = ns, _addr_seed = seed, _randoms = rs, _node_children = cs } =
    (a, t{ _nodes = ns', _addr_seed = seed', _randoms = rs', _node_children = cs''}) where
        (a, seed') = runUniqueSource (liftM Address fresh) seed
        ns' = M.insert a node ns
        rs' = if isRandomNode node t then S.insert a rs
              else rs
        cs' = addChildOf a (parentAddrs node) cs
        cs'' = M.insert a S.empty cs'

addChildOf :: (Ord c, Ord p) => c -> [p] -> M.Map p (S.Set c) -> M.Map p (S.Set c)
addChildOf c ps m = foldl addChild m ps
    where addChild m p = M.adjust (S.insert c) p m

-- Given a valid Trace and an Address that occurs in it, returns the
-- Addresses of the Nodes in the trace that depend upon the value of
-- the node at the given address.
children :: Address -> Trace m -> [Address]
children a t = t ^. node_children . at a & fromJust "Loooking up the children of a nonexistent node" & S.toList

-- If the given Trace is valid, returns a unique SPAddress (distinct
-- from every other SPAddress in the trace) and a valid Trace with the
-- an SPRecord for the given SP added at that SPAddress.
addFreshSP :: SP m -> Trace m -> (SPAddress, Trace m)
addFreshSP sp t@Trace{ _sprs = ss, _spaddr_seed = seed } = (a, t{ _sprs = ss', _spaddr_seed = seed'}) where
    (a, seed') = runUniqueSource (liftM SPAddress fresh) seed
    ss' = M.insert a (spRecord sp) ss

lookupResponse :: SPAddress -> SRId -> Trace m -> Maybe Address
lookupResponse spa srid t = do
  SPRecord { requests = reqs } <- t ^. sprs . at spa
  M.lookup srid reqs

-- Given a valid Trace, and an SPAddress, an SRId, and an Address that
-- occur in it, and assuming (a) the SRId identifies a
-- SimulationRequest made by an application of the SP whose SPAddress
-- is given, and (b) there is no response recorded for that SRId yet,
-- returns a valid Trace that assumes that said SimulationRequest is
-- fulfilled by the Node at the given Address.
insertResponse :: SPAddress -> SRId -> Address -> Trace m -> Trace m
insertResponse spa id a t@Trace{ _sprs = ss } = t{ _sprs = M.insert spa spr' ss } where
        spr' = spr{ requests = M.insert id a reqs }
        spr@SPRecord { requests = reqs } = t ^. sprs . hardix "Inserting response to non-SP" spa

-- Given a valid Trace, an SPAddress in it, and a list of SRIds
-- identifying SimulationRequests made by applications of the SP at
-- that SPAddress that were fulfilled, returns a valid Trace that
-- assumes those SimulationRequests are being removed (by
-- multiplicity).
forgetResponses :: (SPAddress, [SRId]) -> Trace m -> Trace m
forgetResponses (spaddr, srids) t@Trace{ _sprs = ss } = t{ _sprs = M.insert spaddr spr' ss } where
        spr' = spr{ requests = foldl (flip M.delete) reqs srids }
        spr@SPRecord { requests = reqs } = t ^. sprs . hardix "Forgetting responses to non-SP" spaddr

-- Given a valid Trace and an Address that occurs in it, returns the
-- number of times that address has been requested.
numRequests :: Address -> Trace m -> Int
numRequests a t = length $ filter isOutput $ children a t where
    isOutput a' = case M.lookup a' (t^.nodes) of
                    (Just (Output _ _ _ _ _)) -> True
                    (Just _) -> False
                    Nothing -> error "Dangling child"

-- Given the Address of an Output node in it, this is a lens from a
-- valid Trace to that Output node's responses field (which maintains
-- trace validity under insertion of responses, as long as they appear
-- in the Trace).
responsesAt :: Address -> Simple Lens (Trace m) [Address]
responsesAt a = lens _responses addResponses where
    _responses t = t ^. nodes . hardix "Requesting reposnes from a dangling address" a . responses
    addResponses t rs = execState (do
      oldRs <- nodes . ix a . responses <<.= rs
      node_children %= dropChildOf a oldRs
      node_children %= addChildOf a rs) t

----------------------------------------------------------------------
-- Advanced Trace Manipulations                                     --
----------------------------------------------------------------------

-- These manipulations depend upon the values in trace nodes being
-- sensible.

-- TODO Specify what values are "sensible" to have in a Trace's nodes.
-- Caution is advised, because preserving a strong notion of
-- "sensible" would depend upon the interpreted program being
-- completely well-typed, which would be overambitious to try to
-- enforce.

-- Some notes:

-- 5. After any regen, all Request nodes should have pointers to their
--    output nodes (not necessarily during a regen, because the output
--    nodes wish to be created with their fulfilments).

-- 8. After any detach-regen cycle, all nodes should have values.

-- 9. After any regen, the request parents of any Output node should
--    agree with the requests made by its Request node (through the
--    requests map of the SPRecord of their mutual operator).

-- 10. The _randoms should be the set of modifiable random choices.  A
--     node is a random choice iff it is a Request or Output node, and
--     the corresponding part of the SP that is the operator is
--     actually stochastic.  A random choice is modifiable iff it is
--     not constrained by observations, but the latter is currently
--     not detectable from the trace itself (but modifiable choices
--     are a subset of all choices).

-- 11. A trace constructed during the course of executing directives,
--     or by inference on such a trace, should have no garbage.  To
--     wit, all Addresses and SPAddresses should be reachable via
--     Nodes, SRIds, and SPRecords from the Addresses contained in the
--     global environment, or the Addresses of predictions or
--     observations (that have not been retracted).

-- Given that the state is a valid Trace, and the inputs are an
-- SPAddress that occurs in it and a list of Addresses that also occur
-- in it, returns the list of simulation requests that this SP makes
-- when its args are nodes at these Addresses (in order).  The Trace
-- in the state may change, but remains valid.  Fails if the call is
-- ill-typed with respect to the SP.
runRequester :: (Monad m, MonadTrans t, MonadState (Trace m) (t m)) =>
                SPAddress -> [Address] -> t m [SimulationRequest]
runRequester spaddr args = do
  t <- get
  spr@SPRecord { sp = SP{ requester = req, current = a }, srid_seed = seed } <-
      use $ sprs . hardix "Running the requester of a non-SP" spaddr
  (reqs, seed') <- lift $ runUniqueSourceT (runReaderT (asRandomR req a args) t) seed
  sprs . ix spaddr .= spr{ srid_seed = seed' }
  return reqs

-- Given that the state is a valid Trace, and the inputs are an
-- SPAddress that occurs in it and two lists of Addresses that also
-- occur in it, returns the value this SP produces when its args and
-- fulfilments are nodes at these Addresses (in order).  The Trace in
-- the state may change, but remains valid.  Fails if the call is
-- ill-typed with respect to the SP.
runOutputter :: (Monad m, MonadTrans t, MonadState (Trace m) (t m)) =>
                SPAddress -> [Address] -> [Address] -> t m Value
runOutputter spaddr argAs resultAs = do
  SP{ outputter = out, current = st }
    <- uses (sprs . hardix "Running the outputter of a non-SP" spaddr) sp
  t <- get
  let result = asRandomO' out st argAs resultAs t
  v <- case result of
         (Left vact) -> lift vact
         (Right sp) -> do spAddr <- state $ addFreshSP sp
                          return $ Procedure spAddr
  return v

fulfilments :: Address -> Trace m -> [Address]
-- The addresses of the responses to the requests made by the Request
-- node at Address.
fulfilments a t = map (fromJust "Unfulfilled request" . flip M.lookup reqs) $ requestIds node where
    node = t ^. nodes . hardix "Asking for fulfilments of a missing node" a
    SPRecord { requests = reqs } = fromJust "Asking for fulfilments of a node with no operator record" $ operatorRecord node t

absorb :: Node -> SP m -> Trace m -> Double
absorb (Request (Just reqs) _ _ args) SP{log_d_req = (Just f), current = a} _ = f a args reqs
-- This clause is only right if canAbsorb returned True on all changed parents
absorb (Output _ _ _ _ _) SP { outputter = Trivial } _ = 0
absorb (Output (Just v) _ _ args reqs) SP{log_d_out = (Just f), current = a} t = f a args' reqs' v where
    args' = map (fromJust "absorb" . flip lookupNode t) args
    reqs' = map (fromJust "absorb" . flip lookupNode t) reqs
absorb _ _ _ = error "Inappropriate absorb attempt"

absorbAt :: (MonadState (Trace m1) m, MonadWriter LogDensity m) => Address -> m ()
absorbAt a = do
  node <- use $ nodes . hardix "Absorbing at a nonexistent node" a
  sp <- gets $ fromJust "Absorbing at a node with no operator" . operator node
  wt <- gets $ absorb node sp
  tell $ LogDensity wt

-- (Un)Incorporate the value currently at the given address (from)into
-- its operator using the supplied function (which is expected to be
-- either do_inc or do_uninc).  Only applies to Output nodes.
corporate :: (MonadState (Trace m) m1) => String -> (Value -> SP m -> SP m) -> Address -> m1 ()
corporate name f a = do
  node <- use $ nodes . hardix (name ++ "ncorporating the value of a nonexistent node") a
  case node of
    (Output _ _ opa _ _) -> do
      let v = fromJust (name ++ "ncorporating value that isn't there") $ valueOf node
      spaddr <- gets $ fromJust (name ++ "ncorporating value for an output with no operator address") . (fromValueAt opa)
      sp <- gets $ fromJust (name ++ "ncorporating value for an output with no operator") . (operator node)
      sprs . ix spaddr %= \r -> r{sp = f v sp}
    _ -> return ()

do_unincorporate :: (MonadState (Trace m) m1) => Address -> m1 ()
do_unincorporate = corporate "Uni" do_uninc
do_incorporate :: (MonadState (Trace m) m1) => Address -> m1 ()
do_incorporate = corporate "I" do_inc

-- TODO Can I abstract the commonalities between this for requests and
-- the same thing for values?
corporateR :: (MonadState (Trace m) m1) => String -> ([Value] -> [SimulationRequest] -> SP m -> SP m) -> Address -> m1 ()
corporateR name f a = do
  node <- use $ nodes . hardix (name ++ "ncorporating the requests of a nonexistent node") a
  case node of
    (Request reqs _ opa args) -> do
      let rs = fromJust (name ++ "ncorporating requests that aren't there") reqs
      spaddr <- gets $ fromJust (name ++ "ncorporating requests for a requester with no operator address") . (fromValueAt opa)
      sp <- gets $ fromJust (name ++ "ncorporating requests for a requester with no operator") . (operator node)
      t <- get
      let ns = map (fromJust (name ++ "ncorporate requests given dangling address") . flip M.lookup (t^.nodes)) args
          vs = map (fromJust (name ++ "ncorporate requests given valueless argument node") . valueOf) ns
      sprs . ix spaddr %= \r -> r{sp = f vs rs sp}
    _ -> return ()

do_unincorporateR :: (MonadState (Trace m) m1) => Address -> m1 ()
do_unincorporateR = corporateR "Uni" do_unincR
do_incorporateR :: (MonadState (Trace m) m1) => Address -> m1 ()
do_incorporateR = corporateR "I" do_incR

constrain :: (MonadState (Trace m) m1) => Address -> Value -> m1 ()
constrain a v = do
  do_unincorporate a
  nodes . ix a . value .= Just v
  do_incorporate a
  -- TODO What will cause the node to be re-added to the set of random
  -- choices if the constraint is lifted in the future?
  randoms %= S.delete a
  maybe_constrain_parents a v

maybe_constrain_parents :: (MonadState (Trace m) m1) => Address -> Value -> m1 ()
maybe_constrain_parents a v = do
  node <- use $ nodes . hardix "Trying to constrain a non-existent node" a
  case node of
    (Reference _ a') -> constrain a' v
    (Output _ _ _ _ reqs) -> do
      op <- gets $ operator node
      case op of
        Nothing -> error "Trying to constrain an output node with no operator"
        (Just SP{outputter = Trivial}) ->
           case reqs of
             -- TODO Make sure this constraint gets lifted if the
             -- requester is regenerated, even if r0 is ultimately a
             -- reference to some non-brush node.
             (r0:_) -> constrain r0 v
             _ -> error "Trying to constrain a trivial output node with no fulfilments"
        _ -> return ()
    _ -> return ()

----------------------------------------------------------------------
-- Checking structural invariants of traces                         --
----------------------------------------------------------------------

-- TODO Define checkers for invariants 5 and 6.

-- TODO confirm (quickcheck?) that no sequence of trace operations at
-- the appropriate level of abstraction can produce a trace that
-- violates the structural invariants.  (Is rejection sampling a
-- sensible way to generate conforming traces, or do I need to test
-- long instruction sequences?)

traceAddresses :: Trace m -> [Address]
traceAddresses t = parentAddresses t ++ randomChoices t
                   ++ nodeChildrenKeys t ++ nodeChildren t ++ requestedAddresses t

parentAddresses :: Trace m -> [Address]
parentAddresses t = concat $ map parentAddrs $ M.elems $ t ^. nodes
randomChoices :: Trace m -> [Address]
randomChoices t = S.toList $ t ^. randoms
nodeChildrenKeys :: Trace m -> [Address]
nodeChildrenKeys t = M.keys $ t ^. node_children
nodeChildren :: Trace m -> [Address]
nodeChildren t = concat $ map S.toList $ M.elems $ t ^. node_children
requestedAddresses :: Trace m -> [Address]
requestedAddresses t = concat $ map (M.elems . requests) $ M.elems $ t ^. sprs

invalidAddress :: Trace m -> Address -> Bool
invalidAddress t a = not $ isJust $ lookupNode a t

referencedInvalidAddresses :: Trace m -> [TraceProblem]
referencedInvalidAddresses t = map InvalidAddress $ filter (invalidAddress t) $ traceAddresses t

traceSPAddresses :: Trace m -> [SPAddress]
traceSPAddresses t = catMaybes $ map (valueOf >=> fromValue) $ M.elems $ t ^. nodes

referencedInvalidSPAddresses :: Trace m -> [TraceProblem]
referencedInvalidSPAddresses t = map InvalidSPAddress $ filter (invalidSPAddress t) $ traceSPAddresses t

invalidSPAddress :: Trace m -> SPAddress -> Bool
invalidSPAddress t a = t ^. sprs . at a & isJust & not

untrackedChildren :: Trace m -> [TraceProblem]
untrackedChildren t = concat $ map with_unwitting_parents $ t ^. nodes . to M.toList where
    with_unwitting_parents (c,node) = zipWith ParentLostChild (unwitting_parents (c,node)) (repeat c)
    unwitting_parents (c,node) = filter (not . is_child_of c) $ parentAddrs node
    is_child_of c p | c `elem` children p t = True
                    | otherwise = False

overtrackedChildren :: Trace m -> [TraceProblem]
overtrackedChildren t = concat $ map with_unwitting_children $ t ^. node_children . to M.toList where
    with_unwitting_children (p,cs) = zipWith CustodyClaim (repeat p) (unwitting_children (p,cs))
    unwitting_children (p,cs) = filter (not . has_child p) $ S.toList cs
    has_child p c | p `elem` parentAddrs (fromJust "dangling child" $ t ^. nodes . at c) = True
                  | otherwise = False

invalid_freshable :: (Ord a) => (Unique -> a) -> [a] -> UniqueSeed -> Maybe a
invalid_freshable _ [] _ = Nothing
invalid_freshable trans as seed = if max < max' then Nothing else Just max where
    max = maximum as
    (max', _) = runUniqueSource (liftM trans fresh) seed

invalid_srid :: SPRecord m -> Maybe SRId
invalid_srid SPRecord{srid_seed = seed, requests = reqs} = invalid_freshable SRId (M.keys reqs) seed

invalid_seeds :: Trace m -> [TraceProblem]
invalid_seeds t@Trace{_addr_seed = aseed, _spaddr_seed = spaseed, _sprs = sprs} =
    catMaybes $ [addr] ++ [spaddr] ++ srids where
        addr = liftM UnseededAddress $ invalid_freshable Address (traceAddresses t) aseed
        spaddr = liftM UnseededSPAddress $ invalid_freshable SPAddress (traceSPAddresses t) spaseed
        srids = map (liftM UnseededSRId) $ map invalid_srid_seed $ M.toList sprs
        invalid_srid_seed (spa, record) = liftM (spa,) $ invalid_srid record

data TraceProblem = InvalidAddress Address
                  | InvalidSPAddress SPAddress
                  | ParentLostChild Address Address
                  | CustodyClaim Address Address
                  | UnseededAddress Address
                  | UnseededSPAddress SPAddress
                  | UnseededSRId (SPAddress, SRId)
    deriving Show

traceProblems :: Trace m -> [TraceProblem]
traceProblems t = referencedInvalidAddresses t
                  ++ referencedInvalidSPAddresses t
                  ++ untrackedChildren t
                  ++ overtrackedChildren t
                  ++ invalid_seeds t

----------------------------------------------------------------------
-- TODO Checking advanced invariants of traces                      --
----------------------------------------------------------------------

----------------------------------------------------------------------
-- Displaying traces for debugging                                  --
----------------------------------------------------------------------

traceShowTrace :: (Trace m) -> (Trace m)
traceShowTrace t = traceShow (pp t) t

instance Pretty Address where
    pp (Address u) = text "A" <> integer (asInteger u)

instance Pretty SPAddress where
    pp (SPAddress u) = text "SPA" <> integer (asInteger u)

instance Pretty SRId where
    pp (SRId u) = text "SR" <> integer (asInteger u)

instance Pretty TraceProblem where
    pp (InvalidAddress a) = pp a
    pp (InvalidSPAddress a) = pp a
    pp (ParentLostChild p c) = (pp p) <> text " lost child " <> (pp c)
    pp (CustodyClaim p c) = (pp p) <> text " claims child " <> (pp c)
    pp (UnseededAddress a) = (pp a) <> text " not generated from seed"
    pp (UnseededSPAddress a) = (pp a) <> text " not generated from seed"
    pp (UnseededSRId (a,srid)) = (pp a) <> text ", " <> (pp srid) <> text " not generated from seed"

instance Pretty (Trace m) where
    pp t = hang (text "Trace") 1 $
             hang (text "Problems") 1 problems $$
             hang (text "Content") 1 contents $$
             hang (text "SPs") 1 sps where
      problems = pp $ traceProblems t
      contents = sep $ map entry $ M.toList $ t^.nodes
      sps = sep $ map entryS $ M.toList $ t^.sprs
      entry (k,v) = pp k <> colon <> rmark <> pp v
          where rmark = if S.member k $ t^.randoms then text " (R) "
                        else space
      entryS (k,v) = pp k <> colon <+> pp v

instance Pretty Node where
    pp (Constant v) = text "Constant" <+> (parens $ pp v)
    pp (Reference v a) = text "Reference" <+> (parens $ ppDefault "No value" v) <+> pp a
    pp (Request srs outA opA args) =
        text "Request" <+> ppDefault "(No requests)" srs
                 $$ text "out:" <+> ppDefault "none" outA
                 <+> text "oper:" <+> pp opA
                 <+> text "args:" <+> pp args
    pp (Output v reqA opA args reqs) =
        text "Output" <+> parens (ppDefault "No value" v)
                 <+> text "req:" <+> pp reqA
                 <+> text "oper:" <+> pp opA
                 <+> text "args:" <+> pp args
                 <+> text "esrs:" <+> pp reqs

ppDefault :: Pretty a => String -> Maybe a -> Doc
ppDefault _ (Just a) = pp a
ppDefault d Nothing = text d

instance Pretty (SPRecord m) where
    pp SPRecord { sp = SP{current = s}, requests = rs } = text (show s) <+> requests where
      requests = brackets $ sep $ map entry $ M.toList rs
      entry (k,v) = pp k <> colon <> space <> pp v

instance Pretty Value where
    pp (Number d) = double d
    pp (Symbol s) = text s
    pp (List l) = pp l
    pp (Procedure a) = text "Procedure" <+> pp a
    pp (Boolean True) = text "true"
    pp (Boolean False) = text "false"

instance Pretty SimulationRequest where
    pp (SimulationRequest id exp env) = pp id <+> pp exp $$ pp env

instance Pretty Exp where
    pp = text . show

instance Pretty Env where
    pp e = brackets $ sep $ map entry $ M.toList $ effectiveEnv e where
      entry (k,v) = text k <> colon <> space <> pp v
