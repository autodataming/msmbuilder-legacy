import abc
import re
import numpy as np
import warnings
from msmbuilder import io
from msmbuilder.metrics.baseclasses import AbstractDistanceMetric, Vectorized

class RedDimPNorm(Vectorized, AbstractDistanceMetric):
    """
    This is a class for using a reduced dimensionality representation for the trajectory data. A transformation matrix must be generated by some other method
    """

    class ProjectionObject:
        def __init__(self, proj_fn):
            data_dict = io.loadh(proj_fn)

            # We only want to keep the vectors and values that are not complex. This is usually all of them
            # But for some reason when there are PC's in the PCA decomposition that have zero variance (i.e. \Sigma has some zero eigenvalues) 
            # You get complex eigenvalues and eigenvectors. We also want to exclude vectors with eigenvalues greater than 1. I don't know where 
            # These came from unfortunately... And this may indicate a larger issue with this method.
            good_vecs = np.where( ( data_dict['vals'].imag == 0 ) 
                                    & ( data_dict['vals'].real < 1 ) 
                                    & ( np.abs( data_dict['vecs'].imag ).max(axis=0) == 0 ) )[0]
#            good_vecs = np.arange( data_dict['vals'].shape[0] )
            self.vecs = np.array( data_dict['vecs'][:, good_vecs].real)
            self.vals = np.array( data_dict['vals'][ good_vecs ].real.astype(float) ) # These should be real already but have 1E-16j attached to them

            dec_ind = np.argsort( self.vals )[::-1]
            
            self.vecs = np.array( self.vecs[:,dec_ind] )
            self.vals = np.array( self.vals[dec_ind] )
 
            self.red_vecs = self.vecs # These containers will hold the reduced version of the matrix
            self.red_vals = self.vals

        def reduce( self, abs_min=None, num_vecs=None, expl_var=None ):
            
            if num_vecs != None:
                self.red_vecs = self.vecs[:,:num_vecs]
                self.red_vals = self.vals[:num_vecs]
            elif expl_var != None:
                expl_var *= self.vals.sum() # Multiply by total variance to convert from the relative input to the absolute variance scale
                N = np.where( np.cumsum( self.vals ) > expl_var )[0][0] # Get the first index that the total variance is greater than the input var
                self.red_vecs = self.vecs[:,:N]
                self.red_vals = self.vals[:N]
            elif abs_min != None:
                keep_ind = np.where( self.vals >= abs_min )[0] # For whatever reason, passing a tuple to the second axis in an nd.array adds an extra dimension
                self.red_vecs = self.vecs[:,keep_ind]
                self.red_vals = self.vals[keep_ind]
            
            print "Kept %d out of %d total vectors" % ( self.red_vals.shape[0], self.vals.shape[0] )
            print self.red_vals
            return

        def execute( self, ptraj ):
            return np.dot( ptraj.conj(), self.red_vecs )           

    def __init__(self,proj_object_fn,pdb_fn=None,prep_with=None,abs_min=None,num_vecs=None, expl_var=None, metric='euclidean',p=2):
        """Inputs:
        1) proj_obj - A serializer object with keys 'vecs' and 'vals' corresponding to projection vectors and their 
                corresponding eigenvalues. For example, these could be eigenvectors of the covariance metric
                and you can do PCA with this metric.
        2) pdb_fn [ None ] - If using positions, then this must be specified. Otherwise it should be none.
                Note that projection atom positions doesn't work very well in our experience.
        3) prep_with [ None ] - If using positions, this should be none. Otherwise it should be an instance of another metric.
                The prepare_trajectory method of that metric will be used to calculate a certain quantity, e.g. dihedrals, or contacts
        4) metric [ 'euclidean' ] - Should be a valid entry for the Vectorized class (see metrics.Vectorized)
        5) p [ 2 ] - Exponent for the p-norm
        """
        if proj_object_fn[-3:] == 'npy': # This is here because you can pickle an mdp.Node object and use it with this metric
            self.pca = np.load( proj_object_fn )
        else:
            self.pca = self.ProjectionObject( proj_object_fn )
            if num_vecs:
                self.num_vecs = int( num_vecs )
            else:
                self.num_vecs = None
 
            if expl_var:
                self.expl_var = float( expl_var )
            else:
                self.expl_var = None

            if abs_min:
                self.abs_min = float( abs_min )
            else:
                self.abs_min = None

            self.pca.reduce( num_vecs = self.num_vecs, expl_var = self.expl_var, abs_min = self.abs_min ) # this is going to throw and error if you use the mdp.Node object...
 
        self.use_positions = False
        if prep_with:
            self.prep_with = prep_with
        else:
            raise Exception('Must provide one of prep_with or pdbFN')

        super(RedDimPNorm,self).__init__(metric,p)

    def prepare_trajectory(self,trajectory):

        trajectory = self.prep_with.prepare_trajectory( trajectory )
        if len(trajectory.shape) == 3:
            n0,n1,n2 = trajectory.shape
            trajectory = self.pca.execute( trajectory.reshape( n0, n1*n2 ) )
        else:
            trajectory = self.pca.execute( np.array([ frame.flatten() for frame in trajectory ]) ) 
            # The prepared trajectory should be iterable. ONLY RMSD messes this up. If this isn't the case, it's likely the pca.execute will break anyway.

#        trajectory = np.concatenate( (trajectory.real,trajectory.imag), axis=1 ).copy() # copy to make it contiguous memory

        return trajectory

