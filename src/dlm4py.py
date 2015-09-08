'''
This is the python-level interface for the dlm code.
'''

import numpy as np
import sys
from tacs import TACS, elements, constitutive
from mpi4py import MPI
import dlm

class JDVec:
    def __init__(self, xr, xc=None):
        '''
        The vectors that form the M-orthogonal JD subspace.  Note that
        some of the vectors may just consist of real or complex
        components. From the outside, this vector is designed to
        operate using complex values, but internally, it works with
        separate real and complex components. Each real/complex pair
        is combined using 
        '''
        
        self.xr = xr
        self.xc = xc

        return
    
    def copy(self, vec):
        '''Copy the values from vec to self'''

        # Copy the real components
        self.xr.copyValues(vec.xr)

        # Copy the values from the complex components
        if vec.xc is not None:
            self.xc.copyValues(vec.xc)
        else:
            self.xc.zero()

        return
    
    def dot(self, vec):
        '''
        Compute the dot product
        
        self.x^{H}*vec.x
        = (self.xr - j*self.xc)^{T}*(vec.xr + j*vec.xc) = 
        = (self.xr^{T}*vec.xr + self.xc^{T}*vec.xc) + 
        j*(self.xr^{T}*vec.xc - self.xc^{T}*vec.xr)
        '''

        # Do different things, depending on whether both real and
        # complex vector components are defined
        if (self.xc is None) and (vec.xc is None):
            return self.xr.dot(vec.xr) + 0*1j
        elif (self.xc is None):
            return self.xr.dot(vec.xr) + 1j*self.xr.dot(vec.xc)
        elif (vec.xc is None):
            return self.xr.dot(vec.xr) - 1j*self.xc.dot(vec.xr)

        # Everything is defined, compute the full inner product
        dot = (self.xr.dot(vec.xr) + self.xc.dot(vec.xc)
               + 1j*(self.xr.dot(vec.xc) - self.xc.dot(vec.xr)))
               
        return dot

    def axpy(self, alpha, vec):
        '''
        Add self <- self + alpha*vec

        self.xr + 1j*self.xc += (alphar + 1j*alphac)*(vec.xr + 1j*vec.xc)
        '''

        self.xr.axpy(alpha.real, vec.xr)

        # Add the complex part from alpha
        if alpha.imag != 0.0:
            self.xc.axpy(alpha.imag, vec.xr)

        # Add any contributions from the complex vector components
        if vec.xc is not None:
            self.xc.axpy(alpha.real, vec.xc)

            if alpha.imag != 0.0:
                self.xr.axpy(-alpha.imag, vec.xc)

        return

    def scale(self, alpha):
        '''
        Scale the vector of values by a real scalar
        '''
        self.xr.scale(alpha.real)
        if self.xc is not None:
            self.xc.scale(alpha.real)

        return

    def zero(self):
        '''
        Zero the values in the array
        '''

        self.xr.zeroEntries()
        if self.xc is not None:
            self.xc.zeroEntries()

        return


class GMRES:
    def __init__(self, mat, pc, msub):
        '''
        Initialize the GMRES object for the Jacobi--Davidson method
        '''

        # Copy over the problem definitions
        self.mat = mat
        self.pc = pc
        self.msub = msub

        # Allocate the Hessenberg - this allocates a full matrix
        self.H = np.zeros((self.msub+1, self.msub), dtype=np.complex)

        # Allocate small arrays of size m
        self.res = np.zeros(self.msub+1, dtype=np.complex)

        # Store the normal rotations
        self.Qsin = np.zeros(self.msub, dtype=np.complex)
        self.Qcos = np.zeros(self.msub, dtype=np.complex)

        # Allocate the subspaces
        self.W = []
        self.Z = []

        return

    def solve(self, b, x):
        '''
        Solve the linear system
        '''

        # Perform the initialization: copy over b to W[0] and
        # normalize the result - store the entry in res[0]
        self.W[0].copy(b)
        self.res[0] = np.sqrt(self.W[0].dot(self.W[0]))
        self.W[0].scale(1.0/self.res[0])

        # Perform the matrix-vector products
        for i in xrange(self.msub):
            # Apply the preconditioner
            self.pc.apply(self.W[i], self.Z[i])

            # Compute the matrix-vector product
            self.mat.mult(self.Z[i], self.W[i+1])

            # Perform modified Gram-Schmidt orthogonalization
            for j in xrange(i+1):
                self.H[j,i] = self.W[j].dot(self.W[i+1])
                self.W[i+1].axpy(-self.H[j,i], self.W[j])

            # Compute the norm of the orthogonalized vector and
            # normalize it
            self.H[i+1,i] = np.sqrt(self.W[i+1].dot(self.W[i+1]))
            self.W[i+1].scale(1.0/H[i+1,i])

            # Apply the Givens rotations
            for j in xrange(i):
                h1 = self.H[j, i]
                h2 = self.H[j+1, i]
                self.H[j, i] = h1*self.Qcos[j] + h2*self.Qsin[j]
                self.H[j+1, i] = -h1*self.Qsin[j] + h2*self.Qcos[j]

            # Compute the contribution to the Givens rotation
            # for the current entry
            h1 = self.H[i, i]
            h2 = self.H[i+1, i]

            # Modification for complex from Saad pg. 193
            sq = np.sqrt(abs(h1)**2 + h2*h2)
            self.Qsin[i] = h2/sq
            self.Qcos[i] = h1/sq

            # Apply the newest Givens rotation to the last entry
            self.H[i, i] = h1*self.Qcos[i] + h2*self.Qsin[i]
            self.H[i+1, i] = -h1*self.Qsin[i] + h2*self.Qcos[i]

            # Update the residual
            h1 = res[i]
            res[i] = h1*self.Qcos[i]
            res[i+1] = -h1*self.Qsin[i]

        # Compute the linear combination
        for i in xrange(niters-1, -1, -1):
            for j in xrange(i+1, niters):
                res[i] -= self.H[i, j]*res[j]
            res[i] /= self.H[i, i]

        # Form the linear combination
        x.zero()
        for i in xrange(niters):
            x.axpy(res[i], self.Z[i])

        return niters

class DLM:
    def __init__(self, is_symmetric=1, epstol=1e-12):
        '''
        Initialize the internal mesh.
        '''

        # A flag that indicates whether this geometry is symmetric or
        # not. Symmetric by default.
        self.is_symmetric = is_symmetric
        self.use_steady_kernel = True
        self.epstol = epstol
        
        # The influence coefficient matrix
        self.Dtrans = None

        # The total number of panels and nodes
        self.npanels = 0
        self.nnodes = 0

        # The points required for analysis
        self.Xi = None
        self.Xo = None
        self.Xr = None
        self.dXav = None

        # The surface connectivity - required for visualization and
        # load/displacement transfer
        self.X = None
        self.conn = None

        # Set placeholder objects for flutter objects
        self.temp = None
        self.Vm = None

        return

    def addMeshSegment(self, n, m, span, root_chord, x0=[0, 0, 0], 
                       sweep=0.0, dihedral=0.0, taper_ratio=1.0):
        '''
        Add a segment to the current set of mesh points. Note that
        once a segment is added, you cannot delete it.
        
        input:
        n:           number of panels along the spanwise direction
        m:           number of panels along the chord-wise direction
        root_chord:  segment root chord (at x0)
        x0:          (x, y, z) position
        sweep:       sweep angle in radians
        dihedral:    dihedral angle in radians
        taper_ratio: the segment taper ratio
        '''

        npanels = n*m
        x0 = np.array(x0)
        Xi = np.zeros((npanels, 3))
        Xo = np.zeros((npanels, 3))
        Xr = np.zeros((npanels, 3))
        dXav = np.zeros(npanels)

        # Compute the inboard/outboard and receiving point locations
        dlm.computeinputmeshsegment(n, m, x0, span, dihedral, sweep,
                                    root_chord, taper_ratio, 
                                    Xi.T, Xo.T, Xr.T, dXav)

        conn = np.zeros((n*m, 4), dtype=np.intc)
        X = np.zeros(((n+1)*(m+1), 3))

        # Compute the x,y,z surface locations
        dlm.computesurfacesegment(n, m, x0, span, dihedral, sweep,
                                  root_chord, taper_ratio, X.T, conn.T)

        # Append the new mesh components
        if self.Xi is None:
            # Set the mesh locations if they do not exist already
            self.Xi = Xi
            self.Xo = Xo
            self.Xr = Xr
            self.dXav = dXav

            # Set the surface mesh locations/connectivity
            self.X = X
            self.conn = conn
        else:
            # Append the new mesh locations
            self.Xi = np.vstack((self.Xi, Xi))
            self.Xo = np.vstack((self.Xo, Xo))
            self.Xr = np.vstack((self.Xr, Xr))
            self.dXav = np.hstack((self.dXav, dXav))

            # Append the new connectivity and nodes
            self.X = np.vstack((self.X, X))
            self.conn = np.vstack((self.conn, conn + self.nnodes))

        # Set the new number of nodes/panels
        self.npanels = self.Xi.shape[0]
        self.nnodes = self.X.shape[0]

        return

    def computeFlutterMat(self, U, p, qinf, Mach,
                          nvecs, Kr, vwash, dwash, modes):
        '''
        Compute the (reduced) flutter matrix given as follows:

        Fr(p) = p**2*Ir + Kr - qinf*modes^{T}*D^{-1}*wash  
        '''

        # Compute the contribution from the reduced structural problem
        F = np.zeros((nvecs, nvecs), dtype=np.complex)
        F[:,:] = Kr[:,:]

        # Add the term I*p**2 from the M-orthonormal subspace
        for i in xrange(nvecs):
            F[i, i] += p**2

        # Compute the influence coefficient matrix
        self.computeInfluenceMatrix(U, p.imag, Mach)

        # Compute the boundary condition: -1/U*(dh/dt + U*dh/dx)
        # dwash = -dh/dx, vwash = -dh/dt 
        wash = p*vwash/U + dwash

        # Solve for the normal wash due to the motion of the wing
        # through the flutter mode
        Cp = np.linalg.solve(self.Dtrans.T, wash)

        # Compute the forces due to the flutter motion
        forces = np.zeros((self.nnodes, 3), dtype=np.complex)

        # Add the forces to the vector
        for i in xrange(nvecs):
            forces[:,:] = 0.j
            dlm.addcpforces(qinf, Cp[:,i], self.X.T, self.conn.T, forces.T)
            F[:,i] += np.dot(modes.T, forces.flatten())
            
        return F

    def computeFlutterDet(self, U, p, qinf, Mach,
                          nvecs, Kr, vwash, dwash, modes, omega):
        '''
        Compute the determinant of the reduced flutter matrix:
        
        det Fr(p)
        
        This code first calls the code to compute the flutter matrix,
        then evaluates the determinant.
        '''

        F = self.computeFlutterMat(U, p, qinf, Mach, nvecs, 
                                   Kr, vwash, dwash, modes)
        return np.linalg.det(F)/(omega**(2*nvecs))
    

    def computeStaticLoad(self, aoa, U, qinf, Mach, 
                          nvecs, omega, modes, filename=None):
        '''
        Compute the static loads due 
        '''

        # Compute the influence coefficient matrix
        omega_aero = 0.0
        self.computeInfluenceMatrix(U, omega_aero, Mach)

        # Evaluate the right-hand-side
        w = np.zeros(self.npanels, dtype=np.complex)
            
        # Compute a right hand side
        dlm.computeperiodicbc(w, aoa, omega_aero, self.Xi.T, self.Xo.T)

        # Solve the resulting right-hand-side
        Cp = np.linalg.solve(self.Dtrans.T, w)

        # Compute the forces
        forces = np.zeros((self.nnodes, 3), dtype=np.complex)
        dlm.addcpforces(qinf, Cp, self.X.T, self.conn.T, forces.T)

        # Compute the generalized displacements
        u = np.dot(modes.T, forces.flatten())/omega**2

        # Compute the full set of diplacements
        udisp = np.dot(modes, u).real

        if not filename is None:
            self.writeToFile(Cp, filename, udisp.reshape(self.nnodes, 3))
        
        return

    def computeInfluenceMatrix(self, U, omega_aero, Mach):
        '''
        Compute the influence coefficient matrix
        '''

        if self.Dtrans is None or self.Dtrans.shape[0] < self.npanels:
            # Allocate the influence coefficient matrix
            self.Dtrans = np.zeros((self.npanels, self.npanels), dtype=np.complex)

        # Compute the influence coefficient matrix
        dlm.computeinfluencematrix(self.Dtrans.T, omega_aero, U, Mach,
                                   self.Xi.T, self.Xo.T, self.Xr.T, self.dXav,
                                   self.is_symmetric, self.use_steady_kernel, 
                                   self.epstol)
        return
    
    def solve(self, U, aoa=0.0, omega=0.0, Mach=0.0, w=None):
        '''
        Solve the linear system (in the frequency domain)
        '''

        # Compute the influence coefficient matrix
        self.computeInfluenceMatrix(U, omega, Mach)

        if w is None:
            # Evaluate the right-hand-side
            w = np.zeros(self.npanels, dtype=np.complex)
            
            # Compute the normalized downwash
            for i in xrange(self.npanels):
                w[i] = -1.0 - 1j*(omega/U)*self.Xr[i, 0]

        Cp = np.linalg.solve(self.Dtrans.T, w)

        return Cp

    def getModeBCs(self, mode):
        '''
        Transfer the displacements specified at the surface
        coordinates to the normal-component at the receiving points.
        '''

        vwash = np.zeros(self.npanels)
        dwash = np.zeros(self.npanels)
        dlm.getmodebcs(mode.T, self.X.T, self.conn.T, vwash, dwash)

        return vwash, dwash

    def addAeroForces(self, qinf, Cp):
        '''
        Compute the forces on the aerodynamic surface mesh.
        '''

        Cp = np.array(Cp, dtype=np.complex)
        forces = np.zeros((self.nnodes, 3), dtype=np.complex)
        dlm.addcpforces(qinf, Cp, self.X.T, self.conn.T, forces.T)

        return forces        

    def writeToFile(self, Cp, filename='solution.dat', u=None):
        '''
        Write the Cp solution (both the real and imaginary parts)
        to a file for visualization
        '''

        fp = open(filename, 'w')

        if fp:
            fp.write('Title = \"Solution\"\n')
            fp.write('Variables = X, Y, Z, Re(Cp), Im(Cp)\n')
            fp.write('Zone T=wing n=%d e=%d '%(self.nnodes, self.npanels))
            fp.write('datapacking=block ')
            fp.write('zonetype=fequadrilateral ')
            fp.write('varlocation=([4,5]=cellcentered)\n')

            # Write out the panel locations
            if u is None:
                for j in xrange(3):
                    for i in xrange(self.nnodes):
                        fp.write('%e\n'%(self.X[i, j]))
            else:
                for j in xrange(3):
                    for i in xrange(self.nnodes):
                        fp.write('%e\n'%(self.X[i, j] + u[i, j]))

            # Write out the real/imaginary Cp values
            for i in xrange(self.npanels):
                fp.write('%e\n'%(Cp[i].real))
            for i in xrange(self.npanels):
                fp.write('%e\n'%(Cp[i].imag))

            for i in xrange(self.npanels):
                fp.write('%d %d %d %d\n'%(
                        self.conn[i,0]+1, self.conn[i,1]+1,
                        self.conn[i,2]+1, self.conn[i,3]+1))
            
            fp.close()

        return

    def initStructure(self, tacs, load_case=0, max_h_size=0.5,
                      gauss_order=2):
        '''
        Set up the load and displacement transfer object for a general
        TACS finite-element model.
        '''

        # Set the load case number
        self.load_case = load_case

        # Get the communicator from the TACSAssembler object
        self.tacs = tacs
        comm = self.tacs.getMPIComm()

        # Now, set up the load and displacement transfer object
        struct_root = 0
        aero_root = 0

        # Only use the first rank as an aerodynamic processor
        aero_member = 0
        if comm.rank == 0:
            aero_member = 1

        # Get the aerodynamic mesh connectivity
        aero_pts = self.X.flatten()
        aero_conn = self.conn.flatten()

        # Specify the load/displacement transfer data
        self.transfer = TACS.LDTransfer(comm, struct_root, 
                                        aero_root, aero_member,
                                        aero_pts, aero_conn, 
                                        self.tacs, max_h_size, gauss_order)

        # Set the aerodynamic surface nodes
        self.transfer.setAeroSurfaceNodes(aero_pts)

        # Set up the matrices/pc/Krylov solver that will be required
        # for the flutter analysis
        self.mat = tacs.createFEMat()

        # The raw stiffness/mass matrices 
        self.kmat = tacs.createFEMat()
        self.mmat = tacs.createFEMat()

        # Create the preconditioner and the solver object.  Note that
        # these settings are best for a shell-type finite-element
        # model.
        lev = 10000
        fill = 10.0
        reorder_schur = 1
        self.pc = TACS.PcScMat(self.mat, lev, fill, reorder_schur)

        # Create the GMRES object 
        gmres_iters = 10
        nrestart = 0
        isflexible = 0
        self.gmres = TACS.GMRES(self.mat, self.pc, 
                                gmres_iters, nrestart, isflexible)

        return

    def setUpSubspace(self, m, r, sigma=0.0, tol=1e-12,
                      max_iters=5, use_modes=False):
        '''
        Build a subspace for the flutter analysis using a Lanczos
        method. You can specify to either use the Lanczos subspace
        basis or use the eigenvector basis.

        Input:
        m:         the size of the Lanczos subspace
        r:         the number of eigenvectors that must converge
        sigma:     estimate of the frequency 
        tol:       tolerance for the eigenvector solution
        max_iters: maximum number of iterations to use
        use_modes: reduce the subspace to the eigenvectors
        '''

        # Assemble the mass and stiffness matrices
        self.kmat.zeroEntries()
        self.mmat.zeroEntries()
        self.tacs.assembleMatType(self.load_case, self.kmat,
                                  1.0, elements.STIFFNESS_MATRIX, 
                                  elements.NORMAL)
        self.tacs.assembleMatType(self.load_case, self.mmat,
                                  1.0, elements.MASS_MATRIX, 
                                  elements.NORMAL)

        # Create a temporary tacs vector
        if self.temp is None:
            self.temp = self.tacs.createVec()
        
        # Create a list of vectors
        if self.Vm is None:
            self.Vm = []

        # Allocate the Lanczos subspace vectors
        if len(self.Vm) < m:
            lvm = len(self.Vm)
            for i in xrange(lvm, m):
                self.Vm.append(self.tacs.createVec())

        # Initialize Vm as a random set of initial vectors
        self.Vm[0].setRand(-1.0, 1.0)

        # Iterate until we have sufficient accuracy
        eigvecs = np.zeros((m-1, m-1))
        for i in xrange(max_iters):
            alpha, beta = self.lanczos(self.Vm, sigma)

            # Compute the final coefficient
            b0 = beta[-1]

            # Compute the eigenvalues and eigenvectors
            info = dlm.tridiageigvecs(alpha, beta, eigvecs.T)
            
            if info != 0:
                print 'Error in the tri-diagonal eigenvalue solver'

            # Compute the true eigenvalues/vectors
            omega = np.sqrt(1.0/alpha + sigma)
            
            # Argsort the array, and test for convergence of the
            # r-lowest eigenvalues
            indices = np.argsort(omega)
            omega = omega[indices]
            eigvecs = eigvecs[indices,:]

            convrg = True
            for j in xrange(r):
                if np.fabs(b0*eigvecs[j,-1]) > tol:
                    convrg = False

            if convrg:
                break
            else:
                # Make a better guess for sigma
                sigma = 0.95*omega[0]**2
                
                # Form a linear combination of the best r eigenvectors
                weights = np.sum(eigvecs[:r,:], axis=0)
                self.Vm[0].scale(weights[0])
                for j in xrange(m-1):
                    self.Vm[0].axpy(weights[j], self.Vm[j])

                self.Vm[0].applyBCs()

        # Now that we've built Vm, compute the inner product with the
        # K matrix for later useage
        if use_modes:
            self.Qm = []
            for i in xrange(r):
                # Normalize the eigenvectors so that they remain 
                # M-orthonormal
                eigvecs[i,:] /= np.sqrt(np.sum(eigvecs[i,:]**2))
            
                # Compute the full eigenvector
                qr = self.tacs.createVec()
                for j in xrange(m-1):
                    qr.axpy(eigvecs[i,j], self.Vm[j])
                self.Qm.append(qr)

            # Set the values of the stiffness matrix
            self.Kr = np.zeros((r,r))

            # Set the values of stiffness
            for k in xrange(r):
                self.Kr[k,k] = omega[k]**2
        else:
            # Set the stiffness matrix
            self.Kr = np.zeros((m,m))

            for i in xrange(m):
                self.kmat.mult(self.Vm[i], self.temp)
                for j in xrange(i+1):
                    self.Kr[i,j] = self.temp.dot(self.Vm[j])
                    self.Kr[j,i] = self.Kr[i,j]

            # Set the Qm as the subspace
            self.Qm = self.Vm

        # Get the surface modes and the corresponding normal wash
        self.Qm_modes = np.zeros((3*self.nnodes, len(self.Qm)))
        self.Qm_vwash = np.zeros((self.npanels, len(self.Qm)))
        self.Qm_dwash = np.zeros((self.npanels, len(self.Qm)))

        # Extract the natural frequencies of vibration
        disp = np.zeros(3*self.nnodes)
        for k in xrange(len(self.Qm)):
            # Transfer the eigenvector to the aerodynamic surface
            self.transfer.setDisplacements(self.Qm[k])    
            self.transfer.getDisplacements(disp)

            # Compute the normal wash on the aerodynamic mesh
            vk, dk = self.getModeBCs(disp.reshape(self.nnodes, 3))
    
            # Store the normal wash and the surface displacement
            self.Qm_vwash[:,k] = vk
            self.Qm_dwash[:,k] = dk
            self.Qm_modes[:,k] = disp

        # Set the values of omega
        self.omega = omega[:r]

        print 'omega = ', self.omega[:r]

        return

    def lanczos(self, Vm, sigma):
        '''
        Build an M-orthogonal Lanczos subspace using full
        orthogonalization. The full-orthogonalization makes this
        equivalent to Arnoldi, but only the tridiagonal coefficients
        are retained.

        Input:
        Vm:     list of vectors empty vectors except for Vm[0]
        sigma:  estimate of the first natural frequency

        Output:
        Vm:     an M-orthogonal subspace
        '''

        # Allocate space for the symmetric tri-diagonal system
        alpha = np.zeros(len(Vm)-1)
        beta = np.zeros(len(Vm)-1)

        # Compute (K - sigma*M)
        self.mat.copyValues(self.kmat)
        self.mat.axpy(-sigma, self.mmat)
        
        # Factor the stiffness matrix (K - sigma*M)
        self.pc.factor()

        # Apply the boundary conditions to make sure that the 
        # initial vector satisfies them
        Vm[0].applyBCs()

        # Scale the initial vector
        self.mmat.mult(Vm[0], self.temp)
        b0 = np.sqrt(Vm[0].dot(self.temp))
        Vm[0].scale(1.0/b0)

        # Execute the orthogonalization
        for i in xrange(len(Vm)-1):
            # Compute V[i+1] = (K - sigma*M)^{-1}*M*V[i]
            self.mmat.mult(Vm[i], self.temp)
            self.gmres.solve(self.temp, Vm[i+1])
            
            # Make sure that the boundary conditions are enforced
            # fully
            Vm[i+1].applyBCs()

            # Perform full modified Gram-Schmidt orthogonalization
            # with mass-matrix inner products
            for j in xrange(i, -1, -1):
                # Compute the inner product
                self.mmat.mult(Vm[i+1], self.temp)
                h = Vm[j].dot(self.temp)
                Vm[i+1].axpy(-h, Vm[j])

                if i == j:
                    alpha[i] = h
            
            # Compute the inner product w.r.t. itself
            self.mmat.mult(Vm[i+1], self.temp)
            beta[i] = np.sqrt(Vm[i+1].dot(self.temp))
            Vm[i+1].scale(1.0/beta[i])

        return alpha, beta

    def computeFrozenDeriv(self, rho, Uval, Mach, p, num_design_vars):
        '''
        Compute the frozen derivative: First, find the (approx) left
        and right eigenvectors associated with the solution. This
        involves assembling the matrix:
        
        Fr(p) = p^2*Ir + Kr - qinf*Ar(p).

        Then finding the left- and right-eigenvectors associated with
        the eigenvalue closest to zero.
        '''

        # Evaluate the flutter matrix
        qinf = 0.5*rho*Uval**2
        Fr = self.computeFlutterMat(Uval, p, qinf, Mach, len(self.Qm), 
                                    self.Kr, self.Qm_vwash, self.Qm_dwash, 
                                    self.Qm_modes)

        # Duplicate the values stored in the matrix Fr
        Fr_destroyed = np.array(Fr)

        # Compute all of the left- and right- eigenvectors
        m = len(self.Qm)
        eigs = np.zeros(m, dtype=np.complex) 
        Zl = np.zeros((m, m), dtype=np.complex) 
        Zr = np.zeros((m, m), dtype=np.complex) 
        dlm.alleigvecs(Fr_destroyed.T, eigs, Zl.T, Zr.T)

        # Determine what vectors we should use - this is an educated
        # guess, the smallest eigenvalue/eigenvector triplet 
        k = np.argmin(abs(eigs))
        eig = eigs[k]
        zl = Zl[k,:]
        zr = Zr[k,:]

        # Using the eigenvectors compute the real/complex left
        # eigenvectors
        vr = self.tacs.createVec()
        vc = self.tacs.createVec()
        for i in xrange(m):
            vr.axpy(zl[i].real, self.Qm[i])
            vc.axpy(zl[i].imag, self.Qm[i])

        # Compute the linear combination for the right eigenvector
        ur = self.tacs.createVec()
        uc = self.tacs.createVec()
        for i in xrange(m):
            ur.axpy(zr[i].real, self.Qm[i])
            uc.axpy(zr[i].imag, self.Qm[i])

        # Do an error check here - is this any good???
        self.mmat.mult(vr, self.temp)
        err = ur.dot(self.temp) + 1j*self.temp.dot(uc)
        self.mmat.mult(vc, self.temp)
        err += uc.dot(self.temp) + 1j*self.temp.dot(ur)
        err -= 1.0

        print 'Orthogonality error ', err

        # Compute all of the derivatives
        mrr = np.zeros(num_design_vars)
        mrc = np.zeros(num_design_vars)
        mcr = np.zeros(num_design_vars)        
        mcc = np.zeros(num_design_vars)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.MASS_MATRIX, vr, ur, mrr)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.MASS_MATRIX, vc, ur, mcr)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.MASS_MATRIX, vr, uc, mrc)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.MASS_MATRIX, vc, uc, mcc)

        # Compute all of the derivatives
        krr = np.zeros(num_design_vars)
        krc = np.zeros(num_design_vars)
        kcr = np.zeros(num_design_vars)        
        kcc = np.zeros(num_design_vars)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.STIFFNESS_MATRIX, vr, ur, krr)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.STIFFNESS_MATRIX, vc, ur, kcr)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.STIFFNESS_MATRIX, vr, uc, krc)
        self.tacs.evalMatDVSensInnerProduct(self.load_case, 1.0,
                                            elements.STIFFNESS_MATRIX, vc, uc, kcc)
        
        # Evaluate the (approximate) derivative of F(p) w.r.t. p
        dh = 1j*1e-6
        dFdp = self.computeFlutterMat(Uval, p + dh, qinf, Mach, len(self.Qm), 
                                      self.Kr, self.Qm_vwash, self.Qm_dwash, 
                                      self.Qm_modes)
        dFdp = (dFdp - Fr)/dh

        # Compute the inner product 
        zlh = zl.conjugate()
        fact = np.dot(zlh, np.dot(dFdp, zr))

        # Finish the derivative
        deriv = (p**2*((mrr + mcc) + (mrc - mcr)) + 
                 (krr + kcc) + 1j*(krc - kcr))/fact

        return deriv

    def computeFlutterMode(self, rho, Uval, Mach, kmode, pinit=None, 
                           max_iters=20, tol=1e-12):
        '''
        Given the velocity, compute the lowest frequency
        '''

        # Provide an initial estimate of the frequency
        if pinit is None:
            p1 = -1.0 + 1j*self.omega[kmode]
            p2 = -1.0 + 1j*(1e-3 + self.omega[kmode])
        else:
            p1 = 1.0*pinit
            p2 = 1.0*pinit + 1j*1e-3

        # Compute the dynamic pressure
        qinf = 0.5*rho*Uval**2

        # Compute the flutter determinant
        det1 = self.computeFlutterDet(Uval, p1, qinf, Mach,
                                      len(self.Qm), self.Kr,
                                      self.Qm_vwash, self.Qm_dwash, 
                                      self.Qm_modes, self.omega[kmode])
        det2 = self.computeFlutterDet(Uval, p2, qinf, Mach,
                                      len(self.Qm), self.Kr,
                                      self.Qm_vwash, self.Qm_dwash, 
                                      self.Qm_modes, self.omega[kmode])

        # Perform the flutter determinant iteration
        max_iters = 50
        det0 = 1.0*det1
        for k in xrange(max_iters):
            # Compute the new value of p
            pnew = (p2*det1 - p1*det2)/(det1 - det2)

                    # Move p2 to p1
            p1 = 1.0*p2
            det1 = 1.0*det2

            # Move pnew to p2 and compute pnew
            p2 = 1.0*pnew
            det2 = self.computeFlutterDet(Uval, p2, qinf, Mach,
                                          len(self.Qm), self.Kr,
                                          self.Qm_vwash, self.Qm_dwash, 
                                          self.Qm_modes, self.omega[kmode])
                    
            # Print out the iteration history for impaitent people
            if k == 0:
                print '%4s %10s %10s %10s'%(
                    'Iter', 'Det', 'Re(p)', 'Im(p)') 
            print '%4d %10.2e %10.6f %10.6f'%(
                k, abs(det2), p2.real, p2.imag)

            print p2

            if abs(det2) < tol*abs(det0):
                break

        return p2

    def velocitySweep(self, rho, Uvals, Mach, nmodes):
        '''
        Use the basis stored in Qm to perform a sweep of the
        velocities.
        '''

        # Allocate the eigenvalue at all iterations
        nvals = len(Uvals)
        pvals = np.zeros((nmodes, nvals), dtype=np.complex)

        # Now, evalue the flutter determinant at all iterations
        for kmode in xrange(nmodes):
            for i in xrange(nvals):
                qinf = 0.5*rho*Uvals[i]**2
    
                # Compute an estimate of p based on the lowest natural
                # frequency
                if i == 0:
                    eps = 1e-3
                    p1 = -0.1 + 1j*self.omega[kmode]
                    p2 = p1 + (eps + 1j*eps)
                elif i == 1:
                    eps = 1e-3
                    p1 = 1.0*pvals[kmode,0]
                    p2 = p1 + (eps + 1j*eps)

                # The following code tries to extrapolate the next
                # point
                elif i == 2:
                    eps = 1e-3
                    p1 = 2.0*pvals[kmode,i-1] - pvals[kmode,i-2]
                    p2 = p1 + (eps + 1j*eps)
                else: 
                    eps = 1e-3
                    p1 = 3.0*pvals[kmode,i-1] - 3.0*pvals[kmode,i-2] + pvals[kmode,i-3]
                    p2 = p1 + (eps + 1j*eps)

                # Compute the flutter determinant
                det1 = self.computeFlutterDet(Uvals[i], p1, qinf, Mach,
                                              len(self.Qm), self.Kr,
                                              self.Qm_vwash, self.Qm_dwash, 
                                              self.Qm_modes, self.omega[kmode])
                det2 = self.computeFlutterDet(Uvals[i], p2, qinf, Mach,
                                              len(self.Qm), self.Kr,
                                              self.Qm_vwash, self.Qm_dwash, 
                                              self.Qm_modes, self.omega[kmode])

                # Perform the flutter determinant iteration
                max_iters = 50
                det0 = 1.0*det1
                for k in xrange(max_iters):
                    # Compute the new value of p
                    pnew = (p2*det1 - p1*det2)/(det1 - det2)

                    # Move p2 to p1
                    p1 = 1.0*p2
                    det1 = 1.0*det2

                    # Move pnew to p2 and compute pnew
                    p2 = 1.0*pnew
                    det2 = self.computeFlutterDet(U[i], p2, qinf, Mach,
                                                  len(self.Qm), self.Kr,
                                                  self.Qm_vwash, self.Qm_dwash, 
                                                  self.Qm_modes, self.omega[kmode])
                    
                    # Print out the iteration history for impaitent people
                    if k == 0:
                        print '%4s %10s %10s %10s'%(
                            'Iter', 'Det', 'Re(p)', 'Im(p)') 
                    print '%4d %10.2e %10.6f %10.6f'%(
                        k, abs(det2), p2.real, p2.imag)

                    if abs(det2) < 1e-6*abs(det0):
                        break

                # Store the final value of p
                pvals[kmode, i] = p2

            print '%4s %10s %10s %10s'%(
                'Iter', 'U', 'Re(p)', 'Im(p)')
            print '%4d %10.6f %10.6f %10.6f'%(
                i, U[i], pvals[kmode,i].real, pvals[kmode,i].imag)

        # Return the final values
        return pvals

